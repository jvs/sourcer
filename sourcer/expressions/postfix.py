from outsourcer import Code

from . import utils
from .constants import BREAK, POS, RESULT, STATUS
from .precedence import OperatorPrecedenceRule


class Postfix(OperatorPrecedenceRule):
    num_blocks = 3

    def _compile(self, out):
        with utils.if_succeeds(out, self.operand):
            staging = out.var('staging', RESULT)
            checkpoint = out.var('checkpoint', POS)

            with out.WHILE(True):
                self.operators.compile(out)

                with out.IF(STATUS):
                    out += staging << Code('Postfix')(staging, RESULT)
                    out += checkpoint << POS

                with out.ELSE():
                    out += POS << checkpoint
                    out += RESULT << staging
                    out += STATUS << True
                    out += BREAK
