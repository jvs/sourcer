import typing

from outsourcer import Code

from . import utils
from .base import Expression
from .constants import POS, RESULT, STATUS, TEXT


class Regex(Expression):
    num_blocks = 1

    def __init__(self, pattern, ignore_case=False):
        if isinstance(pattern, typing.Pattern):
            pattern = pattern.pattern
        if not isinstance(pattern, (bytes, str)):
            raise TypeError('Expected bytes or str')
        self.pattern = pattern
        self.skip_ignored = False
        self.ignore_case = ignore_case

    def __str__(self):
        pattern = self.pattern
        if isinstance(pattern, bytes):
            pattern = pattern.decode('ascii')

        pattern = pattern.replace('\\', '\\\\')
        flag = 'i' if self.ignore_case else ''
        return f'/{pattern}/{flag}'

    def can_partially_succeed(self):
        return False

    def _compile(self, out):
        flags = '_IGNORECASE' if self.ignore_case else '0'
        bound_method = f'_compile_re({self.pattern!r}, flags={flags}).match'
        matcher = out.define_global_constant('matcher', Code(bound_method))

        match = out.var('match', matcher(TEXT, POS))
        end = match.end()

        with out.IF(match):
            out += RESULT << match.group(0)
            out += POS << (utils.skip_ignored(end) if self.skip_ignored else end)
            out += STATUS << True

        with out.ELSE():
            out += RESULT << self.error_func()
            out += STATUS << False

    def complain(self):
        return f'Expected to match the regular expression /{self.pattern}/'
