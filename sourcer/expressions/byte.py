from outsourcer import Code

from . import utils
from .base import Expression
from .constants import POS, RESULT, STATUS, TEXT


class Byte(Expression):
    def __init__(self, value):
        if not isinstance(value, int):
            raise TypeError(f'Expected int. Received: {type(value)}.')

        if not (0x00 <= value <= 0xFF):
            raise ValueError(
                f'Expected integer in the range [0, 255]. Received: {value!r}.'
            )

        self.value = value
        self.skip_ignored = False
        self.num_blocks = 1

    def __str__(self):
        return hex(self.value)

    def always_succeeds(self):
        return False

    def can_partially_succeed(self):
        return False

    def argumentize(self, out, flags):
        wrap = Code('_wrap_byte_literal')
        value = self.argumentize(out, flags)
        return out.var('arg', wrap(self.value, value))

    def constantize(self):
        return hex(self.value)

    def _compile(self, out, flags):
        LEN = Code('len')
        has_byte = POS < LEN(TEXT)
        is_match = TEXT[POS] == self.value

        with out.IF(Code(has_byte, ' and ', is_match)):
            out += RESULT << self.value
            end = POS + 1

            if self.skip_ignored:
                out += POS << utils.skip_ignored(end, flags)
            else:
                out += POS << end

            out += STATUS << True

        with out.ELSE():
            out += RESULT << self.error_func()
            out += STATUS << False

    def complain(self):
        return f'Expected to match the byte value {hex(self.value)}'
