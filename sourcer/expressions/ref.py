from outsourcer import Code, Yield

from . import utils
from .base import Expression
from .constants import CALL, POS, RESULT, STATUS


class Ref(Expression):
    is_commented = False
    is_reference = True
    num_blocks = 0

    def __init__(self, name):
        self.name = name
        self.is_local = False
        self._resolved = None

    @property
    def resolved(self):
        return self.name if self._resolved is None else self._resolved

    def __str__(self):
        return self.name

    def _compile(self, out, flags):
        if flags.uses_context and not self.is_local:
            func = Code(f'_ctx.{self.resolved}')
        else:
            func = Code(self.resolved)

        out += (STATUS, RESULT, POS) << Yield((CALL, func, POS))

    def argumentize(self, out, flags):
        return Code(self.resolved)
