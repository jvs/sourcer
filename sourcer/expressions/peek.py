from . import utils
from .base import Expression
from .constants import POS


class Peek(Expression):
    num_blocks = 1

    def __init__(self, expr):
        self.expr = expr

    def __str__(self):
        return f'Peek({self.expr})'

    def always_succeeds(self):
        return False

    def can_partially_succeed(self):
        return self.expr.can_partially_succeed()

    def _compile(self, out):
        backtrack = out.var('backtrack', POS)

        with utils.if_succeeds(out, self.expr):
            out += POS << backtrack
