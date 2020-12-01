from outsourcer import Code

from . import utils
from .constants import BREAK, POS, RESULT, STATUS
from .precedence import OperatorPrecedenceRule


class Prefix(OperatorPrecedenceRule):
    num_blocks = 2

    def _compile(self, out):
        prev = out.var('prev', None)
        checkpoint = out.var('checkpoint', POS)
        staging = out.var('staging')

        with out.WHILE(True):
            with utils.if_fails(out, self.operators):
                out += POS << checkpoint
                out += BREAK

            out += checkpoint << POS
            step = out.var('step', Code('Prefix')(RESULT, None))

            with out.IF(Code(prev, ' is ', None)):
                out += prev << staging << step

            with out.ELSE():
                out += prev.right << step
                out += prev << step

        self.operand.compile(out)

        with out.IF(Code(STATUS, ' and ', prev)):
            out += prev.right << RESULT
            out += RESULT << staging
