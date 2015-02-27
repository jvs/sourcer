from .expressions import Left, End
from .compiler import *


# This module raises this exception when it cannot parse an input sequence.
class ParseError(Exception): pass


def tokenize(token_syntax, source):
    classes = token_syntax._TokenSyntax__classes
    expression = List(reduce(Or, classes))
    tokens = parse(expression, source)
    return [i for i in tokens if not i.__class__._skip]


def tokenize_and_parse(token_syntax, expression, source):
    tokens = tokenize(token_syntax, source)
    return parse(expression, tokens)


def parse(expression, source):
    whole = Left(expression, End)
    ans = parse_prefix(whole, source)
    return ans.value


def parse_prefix(expression, source):
    is_text = isinstance(source, basestring)
    parser = compile(expression, is_text)
    interpreter = _Interpreter(source)
    return interpreter.run(parser)


class _Interpreter(object):
    def __init__(self, source):
        self.source = source
        self.memo = {}
        self.stack = []

    def run(self, parser):
        ans = self._start(parser, 0)
        while self.stack:
            top = self.stack[-1][-1]
            ans = top.send(ans)
            if isinstance(ans, ParseStep):
                ans = self._start(ans.parser, ans.pos)
            else:
                key = self.stack.pop()[0]
                self.memo[key] = ans
        if ans is ParseFailure:
            raise ParseError()
        else:
            return ans

    def _start(self, parser, pos):
        key = (parser, pos)
        if key in self.memo:
            return self.memo[key]
        self.memo[key] = ParseFailure
        generator = parser(self.source, pos)
        self.stack.append((key, generator))
        return None
