from outsourcer import Code

from .base import Expression
from .constants import RESULT, STATUS


class PythonExpression(Expression):
    is_tagged = False
    is_commented = False
    num_blocks = 0

    def __init__(self, source_code):
        self.source_code = source_code

    def __str__(self):
        return f'`{self.source_code}`'

    def always_succeeds(self):
        return True

    def can_partially_succeed(self):
        return False

    def _compile(self, out):
        out += RESULT << Code(self.source_code)
        out += STATUS << True

    def argumentize(self, out):
        return Code(self.source_code)


class PythonSection:
    def __init__(self, source_code):
        self.source_code = source_code

    def __str__(self):
        return f'```{self.source_code}```'
