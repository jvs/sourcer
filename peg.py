from collections import namedtuple
import re


BinaryOperation = namedtuple('BinaryOperation', 'left, operator, right')
ParseError = object()
ParseResult = namedtuple('ParseResult', 'value, pos')
_Regex = type(re.compile(''))


class ParsingOperand(object):
    def __and__(self, other): return And(self, other)
    def __rand__(self, other): return And(other, self)
    def __or__(self, other): return Or(self, other)
    def __ror__(self, other): return Or(other, self)
    def __invert__(self): return Not(self)


class TermMetaClass(type, ParsingOperand): pass
class Term(ParsingOperand): __metaclass__ = TermMetaClass


class BinaryTerm(Term):
    def __init__(self, left, right):
        self.left = left
        self.right = right


class UnaryTerm(Term):
    def __init__(self, term):
        self.term = term


class Alt(Term):
    def __init__(self, term, separator):
        self.first = term
        self.rest = List(Right(separator, term))
        self.tail = Opt(separator)

    def parse(self, parser, pos):
        triple = (self.first, self.rest, self.tail)
        ans = parser.parse(triple, pos)
        if ans is ParseError:
            return ParseError
        else:
            (first, rest, tail) = ans.value
            return ParseResult([first] + rest, ans.pos)


class And(BinaryTerm):
    def parse(self, parser, pos):
        ans = parser.parse(self.left, pos)
        skip = parser.parse(self.right, pos)
        return ParseError if ParseError in (ans, skip) else ans


class Any(Term):
    def parse(self, parser, pos):
        return (ParseError if pos >= len(parser.source)
            else ParseResult(parser.source[pos], pos + 1))


class Expect(UnaryTerm):
    def parse(self, parser, pos):
        ans = parser.parse(self.term, pos)
        return ans if ans is ParseError else ParseResult(ans.value, pos)


class End(Term):
    def parse(self, parser, pos):
        at_end = (pos == len(parser.source))
        return ParseResult(None, pos) if at_end else ParseError


class Left(BinaryTerm):
    def parse(self, parser, pos):
        pair = (self.left, self.right)
        ans = parser.parse(pair, pos)
        return ans if ans is ParseError else ParseResult(ans.value[0], ans.pos)


class Lift(UnaryTerm):
    def parse(self, parser, pos):
        return parser.parse(self.term, pos)


class List(UnaryTerm):
    def parse(self, parser, pos):
        ans = []
        while True:
            next = parser.parse(self.term, pos)
            if next is ParseError:
                break
            pos = next.pos
            ans.append(next.value)
        return ParseResult(ans, pos)


def Middle(left, middle, right):
    return Right(left, Left(middle, right))


class Not(UnaryTerm):
    def parse(self, parser, pos):
        ans = parser.parse(self.term, pos)
        return ParseResult(None, pos) if ans is ParseError else ParseError


class Opt(UnaryTerm):
    def parse(self, parser, pos):
        ans = parser.parse(self.term, pos)
        return ParseResult(None, pos) if ans is ParseError else ans


class Or(BinaryTerm):
    def parse(self, parser, pos):
        ans = parser.parse(self.left, pos)
        return parser.parse(self.right, pos) if ans is ParseError else ans


class Require(BinaryTerm):
    def parse(self, parser, pos):
        ans = parser.parse(self.left, pos)
        if ans is ParseError or not self.right(ans.value):
            return ParseError
        else:
            return ans


class Right(BinaryTerm):
    def parse(self, parser, pos):
        pair = (self.left, self.right)
        ans = parser.parse(pair, pos)
        return ans if ans is ParseError else ParseResult(ans.value[1], ans.pos)


def Some(term):
    return Require(List(term), bool)


class Struct(Term):
    def __setattr__(self, name, value):
        if not hasattr(self, '<pos>'):
            assert name not in ('<fields>', '<pos>', 'parse')
            if not hasattr(self, '<fields>'):
                object.__setattr__(self, '<fields>', [])
            getattr(self, '<fields>').append((name, value))
        object.__setattr__(self, name, value)

    def parse(self, parser, pos):
        cls = self.__class__
        ans = cls.__new__(cls)
        object.__setattr__(ans, '<pos>', pos)
        if not hasattr(self, '<fields>'):
            return ParseResult(ans, pos)
        for field, value in getattr(self, '<fields>'):
            next = parser.parse(value, pos)
            if next is ParseError:
                return ParseError
            object.__setattr__(ans, field, next.value)
            pos = next.pos
        return ParseResult(ans, pos)


class BaseToken(Term): pass


def Token(pattern_str, skip=False):
    pattern = re.compile(pattern_str)

    class TokenType(BaseToken):
        def parse(self, parser, pos):
            source = parser.source
            if pos < len(source) and isinstance(source[pos], TokenType):
                return ParseResult(source[pos], pos + 1)

            next = parser.parse(pattern, pos)
            if next is ParseError:
                return ParseError
            else:
                ans = TokenType()
                ans.content = source[pos : next.pos]
                ans.skip = skip
                return ParseResult(ans, next.pos)

        def __repr__(self):
            arg = getattr(self, 'content', pattern_str)
            return 'Token(%r)' % arg

    return TokenType


def TokenContent(pattern_str):
    return Transform(Token(pattern_str), lambda token: token.content)


class Transform(Term):
    def __init__(self, term, transform):
        self.term = term
        self.transform = transform

    def parse(self, parser, pos):
        ans = parser.parse(self.term, pos)
        if ans is ParseError:
            return ParseError
        else:
            value = self.transform(ans.value)
            return ParseResult(value, ans.pos)


def Interleave(term, separator):
    step = Right(separator, term)
    return Left(Some(step), separator)


def _associate_left(pair):
    assoc = lambda first, rest: BinaryOperation(first, *rest)
    return reduce(assoc, pair[1], pair[0])


def _associate_right(pair):
    assoc = lambda prev, next: BinaryOperation(next[0], next[1], prev)
    return reduce(assoc, reversed(pair[0]), pair[1])


def LeftAssoc(left, op, right):
    term = (left, Some((op, right)))
    return Transform(term, _associate_left)


def RightAssoc(left, op, right):
    term = (Some((left, op)), right)
    return Transform(term, _associate_right)


class Parser(object):
    def __init__(self, source):
        self.source = source
        self.visiting = set()

    def parse(self, term, pos):
        key = (term, pos)
        if key in self.visiting:
            return ParseError

        self.visiting.add(key)
        try:
            return self._parse(term, pos)
        finally:
            self.visiting.remove(key)

    def _parse(self, term, pos):
        if callable(term) and not isinstance(term, Term):
            term = term()

        if term is None:
            return ParseResult(term, pos)

        if term == '' and isinstance(self.source, basestring):
            return ParseResult(term, pos)

        if isinstance(term, basestring):
            if isinstance(self.source, basestring):
                return self.parse_text_string(term, pos)
            else:
                return self.parse_token_string(term, pos)

        if isinstance(term, _Regex):
            return self.parse_regex(term, pos)

        if isinstance(term, tuple):
            return self.parse_tuple(term, pos)
        else:
            return term.parse(self, pos)

    def parse_regex(self, term, pos):
        if not isinstance(self.source, basestring):
            return ParseError
        m = term.match(self.source[pos:])
        if m is None:
            return ParseError
        else:
            value = m.group(0)
            return ParseResult(value or None, pos + len(value))

    def parse_text_string(self, term, pos):
        end = pos + len(term)
        part = self.source[pos : end]
        return ParseResult(part, end) if part == term else ParseError

    def parse_token_string(self, term, pos):
        if pos >= len(self.source):
            return ParseError
        next = self.source[pos]
        if isinstance(next, BaseToken) and next.content == term:
            return ParseResult(term, pos + 1)
        else:
            return ParseError

    def parse_tuple(self, term, pos):
        ans = []
        for item in term:
            next = self.parse(item, pos)
            if next is ParseError:
                return ParseError
            ans.append(next.value)
            pos = next.pos
        return ParseResult(tuple(ans), pos)


def parse(term, source):
    parser = Parser(source)
    return parser.parse(term, 0)


def parse_all(term, source):
    term = Left(term, End())
    ans = parse(term, source)
    if isinstance(ans, ParseResult):
        return ans.value
    else:
        raise RuntimeError('Parse Error')
