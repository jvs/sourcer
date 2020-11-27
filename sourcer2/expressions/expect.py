from . import utils
from .base import Expression
from .constants import POS, RESULT, STATUS


class Expect(Expression):
    num_blocks = 0

    def __init__(self, expr):
        self.expr = expr

    def __str__(self):
        return f'Expect({self.expr})'

    def always_succeeds(self):
        return self.expr.always_succeeds()

    def can_partially_succeed(self):
        return self.expr.can_partially_succeed()

    def _compile(self, out):
        backtrack = out.var('backtrack', POS)
        with utils.if_succeeds(out, self.expr):
            out += POS << backtrack


class ExpectNot(Expression):
    num_blocks = 1

    def __init__(self, expr):
        self.expr = expr

    def __str__(self):
        return f'ExpectNot({self.expr})'

    def _compile(self, out):
        backtrack = out.var('backtrack', POS)
        self.expr.compile(out)
        out += POS << backtrack

        with out.IF(STATUS):
            out += STATUS << False
            out += RESULT << self.error_func()

        with out.ELSE():
            out += STATUS << True
            out += RESULT << None

    def complain(self):
        return f'Did not expect to match: {self.expr}'
