from outsourcer import Code

from . import utils
from .base import Expression
from .constants import POS, RESULT, STATUS, TEXT


class Str(Expression):
    is_commented = False

    def __init__(self, value):
        if not isinstance(value, (bytes, str)):
            raise TypeError(f'Expected bytes or str. Received: {type(value)}.')
        self.value = value
        self.skip_ignored = False
        self.num_blocks = 0 if not self.value else 1

    def __str__(self):
        return repr(self.value)

    def always_succeeds(self):
        return not self.value

    def can_partially_succeed(self):
        return False

    def argumentize(self, out):
        wrap = Code('_wrap_string_literal')
        value = Expression.argumentize(self, out)
        return out.var('arg', wrap(self.value, value))

    def _compile(self, out):
        if not self.value:
            out += STATUS << True
            out += RESULT << ''
            return

        value = out.var('value', self.value)
        end = out.var('end', POS + len(self.value))

        with out.IF(TEXT[POS : end] == value):
            out += RESULT << value
            out += POS << (utils.skip_ignored(end) if self.skip_ignored else end)
            out += STATUS << True

        with out.ELSE():
            out += RESULT << self.error_func()
            out += STATUS << False

    def complain(self):
        return f'Expected to match the string {self.value!r}'
