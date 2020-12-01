from . import utils
from .base import Expression
from .constants import POS, RESULT, STATUS


class Where(Expression):
    num_blocks = 2

    def __init__(self, expr, predicate):
        self.expr = expr
        self.predicate = predicate

    def __str__(self):
        return utils.infix_str(self.expr, 'where', self.predicate)

    def operand_string(self):
        return f'({self})'

    def _compile(self, out):
        with utils.if_succeeds(out, self.expr):
            arg = out.var('arg', RESULT)

            with utils.if_succeeds(out, self.predicate):
                with out.IF(RESULT(arg)):
                    out += RESULT << arg

                with out.ELSE():
                    out += RESULT << self.error_func()
                    out += STATUS << False

    def complain(self):
        return f'Expected to satisfy the predicate: {self.predicate}'
