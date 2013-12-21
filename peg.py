from collections import namedtuple
import re


# The parser returns a BinaryOperation tuple after successfully parsing a
# LeftAssoc or RightAssoc term.
BinaryOperation = namedtuple('BinaryOperation', 'left, operator, right')

# This module raises this exception when it cannot parse an input sequence.
class ParseError(Exception): pass

# A singleton value used internally to indicate a parse failure.
ParseFailure = object()

# A tuple of (object, int). The object is the parse tree, and the int value
# is the index of the last item consumed by the parser, plus one. (So it's
# the index of the next item that the parser should consume.)
ParseResult = namedtuple('ParseResult', 'value, pos')

# Used to recognize regular expression objects.
RegexType = type(re.compile(''))


class ParsingOperand(object):
    '''
    This mixin-style class adds support for two parsing operators:
        a & b evaluates to And(a, b).
        a | b evaluates to Or(a, b).
    '''
    def __and__(self, other): return And(self, other)
    def __rand__(self, other): return And(other, self)
    def __or__(self, other): return Or(self, other)
    def __ror__(self, other): return Or(other, self)


# These classes add the "&" and "|" parsing operators.
class TermMetaClass(type, ParsingOperand): pass
class Term(ParsingOperand): __metaclass__ = TermMetaClass


class BinaryTerm(Term):
    '''Abstract base class for compound terms that consist of two terms.'''
    def __init__(self, left, right):
        self.left = left
        self.right = right


class UnaryTerm(Term):
    '''Abstract base class for terms that consist of a single term.'''
    def __init__(self, term):
        self.term = term


def Alt(term, separator, allow_trailer=True):
    '''
    Parses a list of terms separated by a separator. Returns the elements
    in a normal list, and drops the separators.
    '''
    rest = List(Right(separator, term))
    tail = Opt(separator) if allow_trailer else None
    triple = (term, rest, tail)
    return Transform(triple, lambda ans: [ans[0]] + ans[1])


class And(BinaryTerm):
    def parse(self, parser, pos):
        ans = parser.parse(self.left, pos)
        skip = parser.parse(self.right, pos)
        return ParseFailure if ParseFailure in (ans, skip) else ans


class Any(Term):
    def parse(self, parser, pos):
        return (ParseFailure if pos >= len(parser.source)
            else ParseResult(parser.source[pos], pos + 1))


class Expect(UnaryTerm):
    def parse(self, parser, pos):
        ans = parser.parse(self.term, pos)
        return ans if ans is ParseFailure else ParseResult(ans.value, pos)


class End(Term):
    def parse(self, parser, pos):
        at_end = (pos == len(parser.source))
        return ParseResult(None, pos) if at_end else ParseFailure


def Interleave(term, separator):
    step = Right(separator, term)
    return Left(Some(step), separator)


def Left(*args):
    return Transform(args, lambda ans: ans[0])


class Lift(UnaryTerm):
    def parse(self, parser, pos):
        return parser.parse(self.term, pos)


class List(UnaryTerm):
    def parse(self, parser, pos):
        ans = []
        while True:
            next = parser.parse(self.term, pos)
            if next is ParseFailure:
                break
            pos = next.pos
            ans.append(next.value)
        return ParseResult(ans, pos)


def Middle(left, middle, right):
    return Right(left, Left(middle, right))


class Not(UnaryTerm):
    def parse(self, parser, pos):
        ans = parser.parse(self.term, pos)
        return ParseResult(None, pos) if ans is ParseFailure else ParseFailure


def Opt(term):
    return Or(term, None)


class Or(BinaryTerm):
    def parse(self, parser, pos):
        ans = parser.parse(self.left, pos)
        return parser.parse(self.right, pos) if ans is ParseFailure else ans


class Require(BinaryTerm):
    def parse(self, parser, pos):
        ans = parser.parse(self.left, pos)
        failed = (ans is ParseFailure) or not self.right(ans.value)
        return ParseFailure if failed else ans


def Right(*args):
    return Transform(args, lambda ans: ans[-1])


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
            if next is ParseFailure:
                return ParseFailure
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
            if next is ParseFailure:
                return ParseFailure
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
        if ans is ParseFailure:
            return ParseFailure
        else:
            value = self.transform(ans.value)
            return ParseResult(value, ans.pos)


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
            return ParseFailure

        self.visiting.add(key)
        try:
            return self._parse(term, pos)
        finally:
            self.visiting.remove(key)

    def _parse(self, term, pos):
        if isinstance(term, TermMetaClass):
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

        if isinstance(term, RegexType):
            return self.parse_regex(term, pos)

        if isinstance(term, tuple):
            return self.parse_tuple(term, pos)
        else:
            return term.parse(self, pos)

    def parse_regex(self, term, pos):
        if not isinstance(self.source, basestring):
            return ParseFailure
        m = term.match(self.source[pos:])
        if m is None:
            return ParseFailure
        else:
            value = m.group(0)
            return ParseResult(value or None, pos + len(value))

    def parse_text_string(self, term, pos):
        end = pos + len(term)
        part = self.source[pos : end]
        return ParseResult(part, end) if part == term else ParseFailure

    def parse_token_string(self, term, pos):
        if pos >= len(self.source):
            return ParseFailure
        next = self.source[pos]
        if isinstance(next, BaseToken) and next.content == term:
            return ParseResult(term, pos + 1)
        else:
            return ParseFailure

    def parse_tuple(self, term, pos):
        ans = []
        for item in term:
            next = self.parse(item, pos)
            if next is ParseFailure:
                return ParseFailure
            ans.append(next.value)
            pos = next.pos
        return ParseResult(tuple(ans), pos)


def parse(term, source, pos=0):
    parser = Parser(source)
    ans = parser.parse(term, pos)
    if ans is ParseFailure:
        raise ParseError()
    else:
        return ans


def parse_all(term, source):
    term = Left(term, End())
    ans = parse(term, source)
    if isinstance(ans, ParseResult):
        return ans.value
    else:
        raise ParseError()
