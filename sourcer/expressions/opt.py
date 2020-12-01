from . import utils
from .base import Expression
from .constants import POS, RESULT, STATUS


class Opt(Expression):
    num_blocks = 1

    def __init__(self, expr):
        self.expr = expr

    def __str__(self):
        return f'Opt({self.expr})'

    def always_succeeds(self):
        return True

    def can_partially_succeed(self):
        return False

    def _compile(self, out):
        backtrack = out.var('backtrack', POS)
        with utils.if_fails(out, self.expr):
            out += POS << backtrack
            out += RESULT << None
            out += STATUS << True
