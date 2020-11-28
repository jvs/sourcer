from outsourcer import Code

from . import utils
from .base import Expression
from .constants import POS, RESULT, STATUS


class Skip(Expression):
    num_blocks = 2

    def __init__(self, *exprs):
        self.exprs = exprs

    def __str__(self):
        return f'Skip({", ".join(str(x) for x in self.exprs)})'

    def always_succeeds(self):
        return True

    def can_partially_succeed(self):
        return False

    def _compile(self, out):
        checkpoint = out.var('checkpoint')

        with utils.breakable(out):
            out += checkpoint << POS

            for expr in self.exprs:
                expr.compile(out)

                if expr.always_succeeds():
                    with out.IF(POS != checkpoint):
                        out += Code('continue')
                    continue

                with out.IF(STATUS):
                    out += Code('continue')

                if expr.can_partially_succeed():
                    with out.ELSE():
                        out += POS << checkpoint

        out += RESULT << None
        out += STATUS << True
