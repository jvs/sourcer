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
            require_separator=False,
        ):
        self.expr = expr
        self.separator = separator
        self.discard_separators = discard_separators
        self.allow_trailer = allow_trailer
        self.allow_empty = allow_empty
        self.require_separator = require_separator

        if self.require_separator and not self.allow_trailer:
            raise Exception(
                f'Invalid settings for {self}: '
                'When require_separator is True, allow_trailer must also be True.'
            )

    def __str__(self):
        if self.discard_separators and self.allow_empty and not self.require_separator:
            op = '/?' if self.allow_trailer else '//'
            return utils.infix_str(self.expr, op, self.separator)

        kw = []

        if not self.discard_separators:
            kw.append('discard_separators=False')

        # Always show the allow_trailer flag.
        kw.append(f'allow_trailer={self.allow_trailer}')

        if not self.allow_empty:
            kw.append('allow_empty=False')

        if self.require_separator:
            kw.append('require_separator=True')

        return f'Sep({self.expr}, {self.separator}, {", ".join(kw)})'

    def operand_string(self):
        return f'({self})'

    def always_succeeds(self):
        return self.allow_empty

    def _compile(self, out, flags):
        staging = out.var('staging', [])
        checkpoint = out.var('checkpoint', POS)

        if self.require_separator:
            saw_separator = out.var('saw_separator', False)

        with out.WHILE(True):
            with utils.if_fails(out, flags, self.expr):
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

            with utils.if_fails(out, flags, self.separator):
                out += BREAK

            if not self.discard_separators:
                out += staging.append(RESULT)

            if self.allow_trailer:
                out += checkpoint << POS

            if self.require_separator:
                out += saw_separator << True

        success = [
            RESULT << staging,
            POS << checkpoint,
            STATUS << True,
        ]

        if self.allow_empty and self.require_separator:
            with out.IF(Code(f'not {staging} or {saw_separator}')):
                out.extend(success)

        elif self.require_separator:
            with out.IF(saw_separator):
                out.extend(success)

        elif self.allow_empty:
            out.extend(success)

        else:
            with out.IF(staging):
                out.extend(success)
