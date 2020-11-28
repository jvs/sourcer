from outsourcer import Code

from . import utils
from .base import Expression
from .constants import BREAK, POS, RESULT, STATUS


class List(Expression):
    num_blocks = 2

    def __init__(self, expr, min_len=None, max_len=None):
        self.expr = expr
        self.min_len = min_len
        self.max_len = max_len
        _check_min_and_max_len(min_len, max_len)

    def __str__(self):
        arg = self.expr.operand_string()

        if self.min_len is None and self.max_len is None:
            op = '*'
        elif self.min_len == 1 and self.max_len is None:
            op = '+'
        elif self.min_len == self.max_len:
            op = f'{{{self.min_len}}}'
        else:
            op = f'{{{self.min_len or 0},{self.max_len}}}'

        return f'{arg}{op}'

    def always_succeeds(self):
        return not self.min_len or self.min_len == '0'

    def can_partially_succeed(self):
        return not self.always_succeeds() and self.expr.can_partially_succeed()

    def _compile(self, out):
        LEN = Code('len')
        staging = out.var('staging', [])

        with out.WHILE(True):
            if self.expr.can_partially_succeed():
                checkpoint = out.var('checkpoint', POS)

            with utils.if_fails(out, self.expr):
                if self.expr.can_partially_succeed():
                    out += POS << checkpoint
                out += BREAK

            out += staging.append(RESULT)

            if self.max_len is not None:
                with out.IF(LEN(staging) == Code(self.max_len)):
                    out += BREAK

        if not self.min_len or self.min_len == '0':
            out += RESULT << staging
            out += STATUS << True
            return

        if self.min_len == 1 or self.min_len == '1':
            condition = staging
        else:
            condition = LEN(staging) >= Code(self.min_len)

        with out.IF(condition):
            out += RESULT << staging
            out += STATUS << True


def _check_min_and_max_len(min_len, max_len):
    if min_len is None or max_len is None:
        return

    try:
        min_len, max_len = int(min_len), int(max_len)
    except ValueError:
        return

    if min_len > max_len:
        raise Exception('Expected min_len to be less than max_len')
