from .base import Expression
from .constants import RESULT, STATUS
from .str import Str


class Fail(Expression):
    num_blocks = 0

    def __init__(self, message=None):
        if isinstance(message, Str):
            message = message.value
        self.message = message

    def __str__(self):
        return 'Fail()' if self.message is None else f'Fail({self.message!r})'

    def _compile(self, out):
        out += RESULT << self.error_func()
        out += STATUS << False

    def complain(self):
        return 'Failed' if self.message is None else str(self.message)
