from . import utils
from .constants import BREAK, POS, RESULT


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
                Infix = Code('Infix')
                out += staging << Infix(staging, operator, RESULT)
                if self.associativity is None:
                    out += BREAK

            with utils.if_fails(out, self.operators):
                out += BREAK

            out += operator << RESULT

        with out.IF_NOT(is_first):
            out += STATUS << True
            out += RESULT << staging
            out += POS << checkpoint
