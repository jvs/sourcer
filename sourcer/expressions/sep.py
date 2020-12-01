from outsourcer import Code

from . import utils
from .base import Expression
from .constants import BREAK, POS, RESULT, STATUS


class Sep(Expression):
    num_blocks = 2

    def __init__(
            self,
            expr,
            separator,
            discard_separators=True,
            allow_trailer=False,
            allow_empty=True,
        ):
        self.expr = expr
        self.separator = separator
        self.discard_separators = discard_separators
        self.allow_trailer = allow_trailer
        self.allow_empty = allow_empty

    def __str__(self):
        op = '/?' if self.allow_trailer else '//'
        return utils.infix_str(self.expr, op, self.separator)

    def operand_string(self):
        return f'({self})'

    def always_succeeds(self):
        return self.allow_empty

    def _compile(self, out):
        staging = out.var('staging', [])
        checkpoint = out.var('checkpoint', POS)

        with out.WHILE(True):
            with utils.if_fails(out, self.expr):
                # If we're not discarding separators, and if we're also not
                # allowing a trailing separator, then we need to pop the last
                # separator off of our list.
                if not self.discard_separators and not self.allow_trailer:
                    # But only pop if staging is not empty.
                    with out.IF(staging):
                        out += staging.pop()
                out += BREAK

            out += staging.append(RESULT)
            out += checkpoint << POS

            with utils.if_fails(out, self.separator):
                out += BREAK

            if not self.discard_separators:
                out += staging.append(RESULT)

            if self.allow_trailer:
                out += checkpoint << POS

        success = [
            RESULT << staging,
            POS << checkpoint,
            STATUS << True,
        ]

        if self.allow_empty:
            out.extend(success)
        else:
            with out.IF(staging):
                out.extend(success)
