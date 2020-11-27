from . import utils
from .base import Expression
from .constants import BREAK, POS, RESULT
from .fail import Fail


class Choice(Expression):
    is_commented = False
    num_blocks = 2

    def __init__(self, *exprs):
        self.exprs = exprs

    def __str__(self):
        return ' | '.join(str(x) for x in self.exprs)

    def operand_string(self):
        return f'({self})'

    def always_succeeds(self):
        return any(x.always_succeeds() for x in self.exprs)

    def can_partially_succeed(self):
        return not self.always_succeeds() and (
            any(x.can_partially_succeed() for x in self.exprs)
        )

    def _compile(self, out):
        needs_err = not self.always_succeeds()
        needs_backtrack = any(x.can_partially_succeed() for x in self.exprs)

        backtrack = out.var('backtrack') if needs_backtrack else None
        farthest_pos = out.var('farthest_pos') if needs_err else None

        if needs_err:
            farthest_err = out.var('farthest_err', self.error_func())

        if needs_err and needs_backtrack:
            out += backtrack << farthest_pos << POS
        elif needs_backtrack:
            out += backtrack << POS
        elif needs_err:
            out += farthest_pos << POS

        with utils.breakable(out):
            for i, expr in enumerate(self.exprs):
                comment = f'Option {i+1}:'
                if expr.always_succeeds():
                    comment += ' (always_succeeds)'
                out.add_comment(comment)

                with utils.if_succeeds(out, expr):
                    if expr.always_succeeds():
                        break
                    else:
                        out += BREAK

                if needs_err and expr.can_partially_succeed():
                    if isinstance(expr, Fail):
                        condition = farthest_pos <= POS
                    else:
                        condition = farthest_pos < POS

                    with out.IF(condition):
                        out += farthest_pos << POS
                        out += farthest_err << RESULT

                if i + 1 < len(self.exprs) and expr.can_partially_succeed():
                    out += POS << backtrack

            if needs_err:
                out += POS << farthest_pos
                out += RESULT << farthest_err

    def complain(self):
        return 'Unexpected input'
