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

# Convenience function.
Regex = re.compile

# Used to recognize regular expression objects.
RegexType = type(Regex(''))

# Special return value used to control the parser.
ParseStep = namedtuple('ParseStep', 'term, pos')


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
    assert terms
    args = tuple(Expect(t) for t in terms[1:]) + (terms[0],)
    return Right(*args)


class Any(Term):
    def parse(self, source, pos):
        yield (ParseFailure if pos >= len(source)
            else ParseResult(source[pos], pos + 1))


class Expect(SimpleTerm):
    def parse(self, source, pos):
        ans = yield ParseStep(self.term, pos)
        yield ans if ans is ParseFailure else ParseResult(ans.value, pos)


class End(Term):
    def parse(self, source, pos):
        at_end = (pos == len(source))
        yield ParseResult(None, pos) if at_end else ParseFailure


def Interleave(term, separator):
    step = Right(separator, term)
    return Left(Some(step), separator)


class Lazy(SimpleTerm):
    def preparse(self):
        if not hasattr(self, 'cached_term'):
            self.cached_term = self.term()
        return self.cached_term


def Left(*args):
    return Transform(args, lambda ans: ans[0])


class List(SimpleTerm):
    def parse(self, source, pos):
        ans = []
        while True:
            next = yield ParseStep(self.term, pos)
            if next is ParseFailure:
                break
            pos = next.pos
            ans.append(next.value)
        yield ParseResult(ans, pos)


def Middle(left, middle, right):
    return Right(left, Left(middle, right))


class Not(SimpleTerm):
    def parse(self, source, pos):
        ans = yield ParseStep(self.term, pos)
        yield ParseResult(None, pos) if ans is ParseFailure else ParseFailure


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

    def parse(self, source, pos):
        for term in self.terms:
            ans = yield ParseStep(term, pos)
            if ans is not ParseFailure:
                yield ans
        yield ParseFailure


class Require(Term):
    def __init__(self, term, condition):
        self.term = term
        self.condition = condition

    def parse(self, source, pos):
        ans = yield ParseStep(self.term, pos)
        failed = (ans is ParseFailure) or not self.condition(ans.value)
        yield ParseFailure if failed else ans


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

    def parse(self, source, pos):
        cls = self.__class__
        ans = cls.__new__(cls)
        object.__setattr__(ans, '<pos>', pos)
        if not hasattr(self, '<fields>'):
            yield ParseResult(ans, pos)
        for field, value in getattr(self, '<fields>'):
            next = yield ParseStep(value, pos)
            if next is ParseFailure:
                yield ParseFailure
            object.__setattr__(ans, field, next.value)
            pos = next.pos
        yield ParseResult(ans, pos)


class Token(Term): pass


def TokenClass(pattern_str, skip=False):
    is_regex = isinstance(pattern_str, RegexType)
    pattern = pattern_str if is_regex else Regex(pattern_str)

    class NewClass(Token):
        def parse(self, source, pos):
            if pos < len(source) and isinstance(source[pos], NewClass):
                yield ParseResult(source[pos], pos + 1)

            next = yield ParseStep(pattern, pos)
            if next is ParseFailure:
                yield ParseFailure
            else:
                ans = NewClass()
                ans.content = source[pos : next.pos]
                yield ParseResult(ans, next.pos)

        def __repr__(self):
            arg = getattr(self, 'content', pattern_str)
            return 'Token(%r)' % arg

    NewClass.skip = skip
    return NewClass


def Content(token):
    return Transform(token, lambda token: token.content)


class Tokenizer(object):
    def __init__(self):
        self.tokens = []

    def __call__(self, pattern_str, skip=False):
        token = TokenClass(pattern_str, skip=skip)
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

    def parse(self, source, pos):
        ans = yield ParseStep(self.term, pos)
        if ans is ParseFailure:
            yield ParseFailure
        else:
            value = self.transform(ans.value)
            yield ParseResult(value, ans.pos)


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
        self.stack = []
        self.instances = {}

    def run(self, term):
        ans = self._start(term, 0)
        while self.stack:
            top = self.stack[-1][-1]
            ans = top.send(ans)
            if isinstance(ans, ParseStep):
                ans = self._start(ans.term, ans.pos)
            else:
                key = self.stack.pop()[0]
                self.memo[key] = ans
        if ans is ParseFailure:
            raise ParseError()
        else:
            return ans

    def _start(self, term, pos):
        term = self._resolve(term)
        key = (term, pos)
        if key in self.memo:
            return self.memo[key]
        self.memo[key] = ParseFailure
        generator = self._parse(term, pos)
        self.stack.append((key, generator))
        return None

    def _resolve(self, term):
        while True:
            if isinstance(term, Lazy):
                term = term.preparse()
            elif isinstance(term, TermMetaClass):
                if term not in self.instances:
                    self.instances[term] = term()
                term = self.instances[term]
            else:
                return term

    def _parse(self, term, pos):
        if term is None:
            return self._parse_nothing(term, pos)

        is_source_str = isinstance(self.source, basestring)

        if term == '' and is_source_str:
            return self._parse_nothing(term, pos)

        if isinstance(term, basestring) and is_source_str:
            return self._parse_text(term, pos)

        if isinstance(term, basestring):
            return self._parse_token(term, pos)

        if isinstance(term, RegexType):
            return self._parse_regex(term, pos)

        if isinstance(term, tuple):
            return self._parse_tuple(term, pos)
        else:
            return term.parse(self.source, pos)

    def _parse_nothing(self, term, pos):
        yield ParseResult(term, pos)

    def _parse_regex(self, term, pos):
        if not isinstance(self.source, basestring):
            yield ParseFailure
        m = term.match(self.source[pos:])
        if m is None:
            yield ParseFailure
        else:
            value = m.group(0)
            yield ParseResult(value or None, pos + len(value))

    def _parse_text(self, term, pos):
        end = pos + len(term)
        part = self.source[pos : end]
        yield ParseResult(term, end) if part == term else ParseFailure

    def _parse_token(self, term, pos):
        if pos >= len(self.source):
            yield ParseFailure
        next = self.source[pos]
        if isinstance(next, Token) and next.content == term:
            yield ParseResult(term, pos + 1)
        else:
            yield ParseFailure

    def _parse_tuple(self, term, pos):
        ans = []
        for item in term:
            next = yield ParseStep(item, pos)
            if next is ParseFailure:
                yield ParseFailure
            ans.append(next.value)
            pos = next.pos
        yield ParseResult(tuple(ans), pos)


def parse_all(term, source):
    term = Left(term, End())
    ans = parse(term, source)
    return ans.value


def parse(term, source):
    parser = Parser(source)
    return parser.run(term)
