from .base import Expression
from .constants import POS, RESULT, STATUS


class Backtrack(Expression):
    num_blocks = 1

    def __init__(self, amount):
        self.amount = int(amount)

    def __str__(self):
        return f'Backtrack({self.amount})'

    def always_succeeds(self):
        return False

    def can_partially_succeed(self):
        return False

    def _compile(self, out, flags):
        with out.IF(POS >= self.amount):
            out += POS << (POS - self.amount)
            out += STATUS << True
            out += RESULT << None

        with out.ELSE():
            out += STATUS << False
            out += RESULT << self.error_func()

    def complain(self):
        return f'Cannot backtrack by {self.amount}, unexpected start of input.'
