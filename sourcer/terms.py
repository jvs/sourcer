from collections import namedtuple


# This module raises this exception when it cannot parse an input sequence.
class ParseError(Exception): pass

# A singleton value used internally to indicate a parse failure.
ParseFailure = object()

# A tuple of (object, int). The object is the parse tree, and the int value
# is the index of the last item consumed by the parser, plus one. (So it's
# the index of the next item that the parser should consume.)
ParseResult = namedtuple('ParseResult', 'value, pos')

# Special return value used to control the parser.
ParseStep = namedtuple('ParseStep', 'term, pos')


class ParsingOperand(object):
    '''
    This mixin-style class adds support for parsing operators::
        a & b  ==  And(a, b)
        a | b  ==  Or(a, b)
        a / b  ==  Alt(a, b, allow_trailer=True)
        a // b ==  Alt(a, b, allow_trailer=False)
        ~a     ==  Opt(a)
        a << b ==  Left(a, b)
        a >> b ==  Right(a, b)
        a ^ b  ==  Require(a, b)
        a * b  ==  Transform(a, b)
        a ** b ==  Bind(a, b)
    '''
    def __and__(self, other): return And(self, other)
    def __rand__(self, other): return And(other, self)
    def __or__(self, other): return Or(self, other)
    def __ror__(self, other): return Or(other, self)
    def __div__(self, other): return Alt(self, other, allow_trailer=True)
    def __rdiv__(self, other): return Alt(other, self, allow_trailer=True)
    def __truediv__(self, other): return Alt(self, other, allow_trailer=True)
    def __rtruediv__(self, other): return Alt(other, self, allow_trailer=True)
    def __floordiv__(self, other): return Alt(self, other, allow_trailer=False)
    def __rfloordiv__(self, other): return Alt(other, self, allow_trailer=False)
    def __invert__(self): return Opt(self)
    def __lshift__(self, other): return Left(self, other)
    def __rlshift__(self, other): return Left(other, self)
    def __rshift__(self, other): return Right(self, other)
    def __rrshift__(self, other): return Right(other, self)
    def __mul__(self, other): return Transform(self, other)
    def __pow__(self, other): return Bind(self, other)
    def __xor__(self, other): return Require(self, other)


# These classes add the "&" and "|" parsing operators.
class TermMetaClass(type, ParsingOperand): pass
class Term(ParsingOperand): __metaclass__ = TermMetaClass


class SimpleTerm(Term):
    '''Abstract base class for terms that consist of a single subterm.'''
    def __init__(self, term):
        self.term = term


class Any(Term):
    '''
    Returns the next element of the input. Fails if the remaining input is
    empty. This class can be used as a term directly, or it can be
    instantiated.

    Example 1::
        from sourcer import Any, parse

        # Parse the number one, then any value, then the number 3.
        # Note that the "Any" term does not need to be instantiated.
        goal = (1, Any, 3)
        ans = parse(goal, [1, 2, 3])
        assert ans == (1, 2, 3)

    Example 2::
        from sourcer import Any, parse

        # Try it again with a the string 'ok' in the middle position.
        # Also, this time try instantiating the "Any" term.
        goal = (1, Any(), 3)
        ans = parse(goal, [1, 'ok', 3])
        assert ans == (1, 'ok', 3)

    Example 3::
        from sourcer import Any, Middle, parse

        # Parse any character surrounded by parentheses,
        # discarding the parentheses.
        goal = Middle('(', Any, ')')
        ans = parse(goal, '(a)')
        assert ans == 'a'
    '''
    @staticmethod
    def parse(source, pos):
        yield (ParseFailure if pos >= len(source)
            else ParseResult(source[pos], pos + 1))


class Backtrack(Term):
    '''
    Moves the current position back by some number of spaces. If the new
    position would be less than zero, then it fails and has no other effect.

    Example::
        from sourcer import *
        # (The ">>" operator means "discard the result from the left operand".)
        goal = Pattern(r'[a-z]+') >> Backtrack(1) >> 'o' >> Some('-')
        ans = parse(goal, 'foo---')
        assert ans == list('---')
    '''
    def __init__(self, count=1):
        self.count = count

    def parse(self, source, pos):
        dst = pos - self.count
        yield ParseFailure if dst < 0 else ParseResult(None, dst)


class Bind(Term):
    def __init__(self, term, continuation):
        self.term = term
        self.continuation = continuation

    def parse(self, source, pos):
        arg = yield ParseStep(self.term, pos)
        if arg is ParseFailure:
            yield ParseFailure
        next = self.continuation(arg.value)
        ans = yield ParseStep(next, arg.pos)
        yield ans


class Expect(SimpleTerm):
    def parse(self, source, pos):
        ans = yield ParseStep(self.term, pos)
        yield ans if ans is ParseFailure else ParseResult(ans.value, pos)


class End(Term):
    @staticmethod
    def parse(source, pos):
        at_end = (pos == len(source))
        yield ParseResult(None, pos) if at_end else ParseFailure


class ForwardRef(SimpleTerm):
    def preparse(self):
        if not hasattr(self, 'cached_term'):
            self.cached_term = self.term()
        return self.cached_term


class Get(Term):
    def __init__(self, name, default=ParseFailure):
        self.name = name
        self.default = default


class Let(Term):
    def __init__(self, **kw):
        assert len(kw) == 1
        self.name = kw.keys()[0]
        self.term = kw.values()[0]


class List(SimpleTerm):
    '''
    Parse a term zero or more times and return the results as a list.

    Example 1::
        from sourcer import *

        # Parse the string 'foo' zero or more times.
        foos = List('foo')

        # Try parsing 'foo' * 3.
        # Assert that we receive a list of three 'foo'.
        ans1 = parse(foos, 'foofoofoo')
        assert ans1 == ['foo', 'foo', 'foo']

        # Try parsing just one 'foo'.
        # Assert that we receive a list of one 'foo'.
        ans2 = parse(foos, 'foo')
        assert ans2 == ['foo']

        # Try parsing the empty string.
        # Assert that we receive the empty list.
        ans3 = parse(foos, '')
        assert ans3 == []

    Example 2::
        from sourcer import *

        # Parse a list of 'foo' followed by a list of 'bar'.
        foos = List('foo')
        bars = List('bar')
        goal = (foos, bars)

        # Try two 'foo' and two 'bar'.
        # Assert that we receive a pair of two lists,
        # one with two 'foo' and another with two 'bar'.
        ans1 = parse(goal, 'foofoobarbar')
        assert ans1 == (['foo', 'foo'], ['bar', 'bar'])

        # Try parsing just the string 'bar'.
        ans2 = parse(goal, 'bar')
        assert ans2 == ([], ['bar'])

        # Try parsing the empty string.
        # Assert that we receive a pair of two empty lists.
        ans3 = parse(goal, '')
        assert ans3 == ([], [])
    '''
    def parse(self, source, pos):
        ans = []
        while True:
            next = yield ParseStep(self.term, pos)
            if next is ParseFailure:
                break
            pos = next.pos
            ans.append(next.value)
        yield ParseResult(ans, pos)


class Literal(Term):
    def __init__(self, value):
        self.value = value

    def parse(self, source, pos):
        is_match = (pos < len(source)) and source[pos] == self.value
        yield ParseResult(self.value, pos + 1) if is_match else ParseFailure


class Not(SimpleTerm):
    def parse(self, source, pos):
        ans = yield ParseStep(self.term, pos)
        yield ParseResult(None, pos) if ans is ParseFailure else ParseFailure


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


class Start(Term):
    @staticmethod
    def parse(source, pos):
        yield ParseResult(None, pos) if pos == 0 else ParseFailure


class Struct(object):
    __metaclass__ = TermMetaClass


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


def Alt(term, separator, allow_trailer=True):
    '''
    Parses a list of terms separated by a separator. Returns the elements
    in a normal list, and drops the separators.
    '''
    rest = List(Right(separator, term))
    tail = Opt(separator) if allow_trailer else None
    triple = (term, rest, tail)
    return Transform(Opt(triple), lambda t: [t[0]] + t[1] if t else [])


def And(left, right):
    return Left(left, Expect(right))


def AnyInst(*cls):
    return Where(lambda x: isinstance(x, cls))


def Left(*args):
    return Transform(args, lambda ans: ans[0])


def Lookback(term, count=1):
    '''
    Moves the current position back by some number of spaces and then applies
    the provided term.
    '''
    return Right(Backtrack(count), term)


def Middle(left, middle, right):
    return Right(left, Left(middle, right))


def Opt(term):
    return Or(term, None)


def Right(*args):
    return Transform(args, lambda ans: ans[-1])


def Some(term):
    return Require(List(term), bool)


def Where(test):
    return Require(Any, test)
