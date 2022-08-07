from . import utils
from .constants import BREAK, POS
from .precedence import OperatorPrecedenceRule


class Mixfix(OperatorPrecedenceRule):
    num_blocks = 2

    def _compile(self, out, flags):
        backtrack = out.var('backtrack', POS)
        with utils.breakable(out):
            with utils.if_succeeds(out, flags, self.operators):
                out += BREAK

            out += POS << backtrack
            self.operand.compile(out, flags)

