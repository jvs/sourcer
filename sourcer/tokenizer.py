import re
from .terms import *
from .parser import parse


def tokenize_and_parse(tokenizer, term, source):
    tokens = tokenizer.run(source)
    return parse(term, tokens)


class Token(object):
    __metaclass__ = TermMetaClass

    def __init__(self, content):
        self.content = content

    def __repr__(self):
        name = self.__class__.__name__
        return '%s(%r)' % (name, self.content)


class Tokenizer(object):
    def __setattr__(self, name, value):
        assert name != '_Tokenizer__classes'
        if not hasattr(self, '_Tokenizer__classes'):
            object.__setattr__(self, '_Tokenizer__classes', [])
        value = TokenClass(name, value)
        self.__classes.append(value)
        object.__setattr__(self, name, value)

    def export(self, dst):
        dst.update(dict((cls.__name__, cls)
            for cls in self.__classes if not cls.skip))

    def run(self, source):
        main = List(Or(*self.__classes))
        ans = parse(main, source)
        return [t for t in ans if not t.skip]


def TokenClass(name, pattern):
    is_skipped = isinstance(pattern, Skip)
    if is_skipped:
        pattern = pattern.pattern
    if isinstance(pattern, basestring):
        pattern = Regex(pattern)

    class NewClass(Token):
        @staticmethod
        def parse(source, pos):
            if pos < len(source) and isinstance(source[pos], NewClass):
                yield ParseResult(source[pos], pos + 1)

            next = yield ParseStep(pattern, pos)
            if next is ParseFailure:
                yield ParseFailure

            match = next.value
            ans = NewClass(match.group(0))
            for k, v in match.groupdict().iteritems():
                setattr(ans, k, v)
            yield ParseResult(ans, next.pos)

    NewClass.__name__ = name
    NewClass.skip = is_skipped
    return NewClass


Regex = re.compile
Skip = namedtuple('Skip', 'pattern')


def AnyChar(pattern):
    assert isinstance(pattern, basestring)
    return Regex('[%s]' % re.escape(pattern))


def Content(token):
    return Transform(token, lambda token: token.content)


def Pattern(pattern):
    return Transform(Regex(pattern), lambda m: m.group(0))


def Verbose(pattern):
    return Regex(pattern, re.VERBOSE)
