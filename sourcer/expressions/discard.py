from . import utils
from .base import Expression
from .constants import BREAK, RESULT


class Discard(Expression):
    num_blocks = 2

    def __init__(self, expr1, expr2, discard_left=True):
        self.expr1 = expr1
        self.expr2 = expr2
        self.discard_left = discard_left

    def __str__(self):
        op = '>>' if self.discard_left else '<<'
        return utils.infix_str(self.expr1, op, self.expr2)

    def operand_string(self):
        return f'({self})'

    def always_succeeds(self):
        return (self.expr1.always_succeeds()
            and self.expr2.always_succeeds())

    def _compile(self, out):
        with utils.breakable(out):
            with utils.if_fails(out, self.expr1):
                out += BREAK

            if self.discard_left:
                self.expr2.compile(out)
            else:
                staging = out.var('staging', RESULT)
                with utils.if_succeeds(out, self.expr2):
                    out += RESULT << staging
