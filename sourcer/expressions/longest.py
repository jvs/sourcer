from . import utils
from .base import Expression
from .constants import POS, RESULT, STATUS
from .fail import Fail


class Longest(Expression):
    is_commented = False
    num_blocks = 2

    def __init__(self, *exprs):
        self.exprs = exprs

    def __str__(self):
        return f'Longest({", ".join(str(x) for x in self.exprs)})'

    def always_succeeds(self):
        return any(x.always_succeeds() for x in self.exprs)

    def can_partially_succeed(self):
        return not self.always_succeeds() and (
            any(x.can_partially_succeed() for x in self.exprs)
        )

    def complain(self):
        return 'Unexpected input'

    def _compile(self, out, flags):
        if not self.exprs:
            return

        if len(self.exprs) == 1:
            self.exprs[0].compile(out, flags)
            return

        needs_err = not self.always_succeeds()

        backtrack = out.var('backtrack')
        farthest_result = out.var('farthest_result')
        farthest_position = out.var('farthest_position')
        has_result = out.var('has_result', initializer=False)

        if needs_err:
            farthest_error_result = out.var('farthest_error_result', self.error_func())
            farthest_error_position = out.var('farthest_error_position', self.error_func())

        if needs_err:
            out += backtrack << farthest_position << farthest_error_position << POS
        else:
            out += backtrack << farthest_position << POS

        for i, expr in enumerate(self.exprs):
            # Go back to the initial position and try the next expression.
            if i > 0:
                out += (POS << backtrack)

            comment = f'Option {i + 1}:'
            if expr.always_succeeds():
                comment += ' (always_succeeds)'
            out.add_comment(comment)

            with utils.if_succeeds(out, flags, expr):
                # If this is the first expression, then we can unconditionally
                # update the farthest result.
                if i == 0:
                    out += (farthest_result << RESULT)
                    out += (farthest_position << POS)
                    out += (has_result << True)
                else:
                    # Otherwise, we need to check the current farthest result.
                    with out.IF_NOT(has_result):
                        out += (farthest_result << RESULT)
                        out += (farthest_position << POS)
                        out += (has_result << True)

                    with out.ELIF(farthest_position < POS):
                        out += (farthest_result << RESULT)
                        out += (farthest_position << POS)

            if needs_err:
                if isinstance(expr, Fail):
                    condition = farthest_error_position <= POS
                else:
                    condition = farthest_error_position < POS

                with out.ELIF(f'not {has_result} and ({condition})'):
                    out += farthest_error_position << POS
                    out += farthest_error_result << RESULT

        with out.IF(has_result):
            out += RESULT << farthest_result
            out += POS << farthest_position
            out += STATUS << True

        if needs_err:
            with out.ELSE():
                out += RESULT << farthest_error_result
                out += POS << farthest_error_position
