from outsourcer import Code

from . import utils
from .base import Expression
from .constants import RESULT


class Let(Expression):
    defines_local = True
    num_blocks = 1

    def __init__(self, name, expr, body):
        self.name = name
        self.expr = expr
        self.body = body

    def __str__(self):
        return f'let {self.name} = {self.expr} in\n{self.body}'

    def operand_string(self):
        return f'({self})'

    def always_succeeds(self):
        return (self.expr.always_succeeds()
            and self.body.always_succeeds())

    def _compile(self, out):
        with utils.if_succeeds(out, self.expr):
            out += Code(self.name) << RESULT
            self.body.compile(out)
