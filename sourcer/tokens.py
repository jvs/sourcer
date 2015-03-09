import re
from .expressions import *


class Token(object):
    __metaclass__ = ExpressionMetaClass

    def __init__(self, content):
        self.content = content

    def __repr__(self):
        name = self.__class__.__name__
        return '%s(%r)' % (name, self.content)


class TokenSyntax(object):
    def __setattr__(self, name, value):
        assert name != '_TokenSyntax__classes'
        if not hasattr(self, '_TokenSyntax__classes'):
            object.__setattr__(self, '_TokenSyntax__classes', [])
        value = _create_token_class(name, value)
        self.__classes.append(value)
        object.__setattr__(self, name, value)


def _create_token_class(name, pattern):
    is_skipped = isinstance(pattern, Skip)
    if is_skipped:
        pattern = pattern.pattern
    if isinstance(pattern, basestring):
        pattern = Regex(pattern)

    class TokenClass(Token): pass
    TokenClass.__name__ = name
    TokenClass._skip = is_skipped
    TokenClass._pattern = pattern
    return TokenClass


Regex = re.compile
Skip = namedtuple('Skip', 'pattern')


def AnyChar(pattern):
    assert isinstance(pattern, basestring)
    return Regex('[%s]' % re.escape(pattern))


def AnyString(*strings):
    return Regex('|'.join(re.escape(i) for i in strings))


def Content(token):
    return Transform(token, lambda token: token.content)


def Pattern(pattern):
    return Transform(Regex(pattern), lambda m: m.group(0))


def Verbose(pattern):
    return Regex(pattern, re.VERBOSE)
