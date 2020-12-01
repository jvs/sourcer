from . import utils
from .base import Expression
from .constants import RESULT


class Apply(Expression):
    num_blocks = 2

    def __init__(self, expr1, expr2, apply_left=False):
        self.expr1 = expr1
        self.expr2 = expr2
        self.apply_left = apply_left

    def __str__(self):
        op = '<|' if self.apply_left else '|>'
        return utils.infix_str(self.expr1, op, self.expr2)

    def operand_string(self):
        return f'({self})'

    def always_succeeds(self):
        return self.expr1.always_succeeds() and self.expr2.always_succeeds()

    def _compile(self, out):
        with utils.if_succeeds(out, self.expr1):
            first = out.var('func' if self.apply_left else 'arg', RESULT)
            with utils.if_succeeds(out, self.expr2):
                result = first(RESULT) if self.apply_left else RESULT(first)
                out += RESULT << result
