from collections import namedtuple
import re


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


class SimpleTerm(Term):
    '''Abstract base class for terms that consist of a single subterm.'''
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
    return Transform(Opt(triple), lambda t: [t[0]] + t[1] if t else [])


def And(*terms):
    if not terms:
        return Lift(None)
    args = tuple(Expect(t) for t in terms[1:]) + (terms[0],)
    return Right(*args)


class Any(Term):
    def parse(self, parser, pos):
        return (ParseFailure if pos >= len(parser.source)
            else ParseResult(parser.source[pos], pos + 1))


class Expect(SimpleTerm):
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


class Lazy(SimpleTerm):
    def parse(self, parser, pos):
        if not hasattr(self, 'cached_term'):
            self.cached_term = self.term()
        return parser.parse(self.cached_term, pos)


def Left(*args):
    return Transform(args, lambda ans: ans[0])


class Lift(SimpleTerm):
    def parse(self, parser, pos):
        return parser.parse(self.term, pos)


class List(SimpleTerm):
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


class Not(SimpleTerm):
    def parse(self, parser, pos):
        ans = parser.parse(self.term, pos)
        return ParseResult(None, pos) if ans is ParseFailure else ParseFailure


def Opt(term):
    return Or(term, None)


class Or(Term):
    def __init__(self, *terms):
        self.terms = []
        # Flatten the list of terms.
        for term in terms:
            if isinstance(term, self.__class__):
                self.terms.extend(term.terms)
            else:
                self.terms.append(term)

    def parse(self, parser, pos):
        for term in self.terms:
            ans = parser.parse(term, pos)
            if ans is not ParseFailure:
                return ans
        return ParseFailure


class Require(Term):
    def __init__(self, term, condition):
        self.term = term
        self.condition = condition

    def parse(self, parser, pos):
        ans = parser.parse(self.term, pos)
        failed = (ans is ParseFailure) or not self.condition(ans.value)
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


def Content(token):
    return Transform(token, lambda token: token.content)


class Tokenizer(object):
    def __init__(self):
        self.tokens = []

    def __call__(self, pattern_str, skip=False):
        token = Token(pattern_str, skip=skip)
        self.tokens.append(token)
        return token

    def run(self, source):
        main = List(Or(*self.tokens))
        ans = parse_all(main, source)
        return [t for t in ans if not t.skip]


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


# Utility function to create a tuple from a variable number of arguments.
pack_tuple = (lambda *args: args)


def LeftAssoc(left, op, right, transform=pack_tuple):
    term = (left, Some((op, right)))
    assoc = lambda first, rest: transform(first, *rest)
    xform = lambda pair: reduce(assoc, pair[1], pair[0])
    return Transform(term, xform)


def RightAssoc(left, op, right, transform=pack_tuple):
    term = (Some((left, op)), right)
    assoc = lambda prev, next: transform(next[0], next[1], prev)
    xform = lambda pair: reduce(assoc, reversed(pair[0]), pair[1])
    return Transform(term, xform)


class Parser(object):
    def __init__(self, source):
        self.source = source
        self.memo = {}

    def parse(self, term, pos):
        key = (term, pos)
        if key in self.memo:
            return self.memo[key]

        self.memo[key] = ParseError
        ans = self._parse(term, pos)
        self.memo[key] = ans
        return ans

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
