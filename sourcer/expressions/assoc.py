from outsourcer import Code

from . import utils
from .constants import BREAK, POS, RESULT, STATUS
from .precedence import OperatorPrecedenceRule


class LeftAssoc(OperatorPrecedenceRule):
    associativity = 'left'
    num_blocks = 2

    def _compile(self, out):
        is_first = out.var('is_first', True)
        staging = out.var('staging', None)
        operator = out.var('operator')

        with out.WHILE(True):
            with utils.if_fails(out, self.operand):
                out += BREAK

            checkpoint = out.var('checkpoint', POS)

            with out.IF(is_first):
                out += is_first << False
                out += staging << RESULT

            with out.ELSE():
                out += staging << Code('Infix')(staging, operator, RESULT)
                if self.associativity is None:
                    out += BREAK

            with utils.if_fails(out, self.operators):
                out += BREAK

            out += operator << RESULT

        with out.IF_NOT(is_first):
            out += STATUS << True
            out += RESULT << staging
            out += POS << checkpoint


class NonAssoc(LeftAssoc):
    associativity = None


class RightAssoc(OperatorPrecedenceRule):
    associativity = 'right'
    num_blocks = 4

    def _compile(self, out):
        backup = out.var('backup', None)
        prev = out.var('prev', None)

        staging = out.var('staging')
        checkpoint = out.var('checkpoint')

        with out.WHILE(True):
            with utils.if_fails(out, self.operand):
                with out.IF(prev):
                    with out.IF(backup):
                        out += backup.right << prev.left
                        out += RESULT << staging

                    with out.ELSE():
                        out += RESULT << prev.left

                    out += POS << checkpoint
                    out += STATUS << True
                out += BREAK

            out += checkpoint << POS
            operand = out.var('operand', RESULT)

            with utils.if_fails(out, self.operators):
                with out.IF(prev):
                    out += prev.right << operand
                    out += RESULT << staging

                with out.ELSE():
                    out += RESULT << operand

                out += POS << checkpoint
                out += STATUS << True
                out += BREAK

            step = Code('Infix')(operand, RESULT, None)

            with out.IF(prev):
                out += backup << prev
                out += backup.right << prev << step

            with out.ELSE():
                out += staging << prev << step
