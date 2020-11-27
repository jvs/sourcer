
class Prefix(OperatorPrecedenceRule):
    num_blocks = 2

    def _compile(self, pb):
        prev = pb.var('prev', Val(None))
        checkpoint = pb.var('checkpoint', POS)
        staging = pb.var('staging')

        with pb.loop():
            with _if_fails(pb, self.operators):
                pb(POS << checkpoint, BREAK)

            pb(checkpoint << POS)
            step = pb.var('step', code.Prefix(RESULT, Val(None)))

            with pb.IF(Code(prev, ' is ', Val(None))):
                pb(prev << staging << step)

            with pb.ELSE():
                pb(prev.right << step, prev << step)

        self.operand.compile(pb)

        with pb.IF(Code(STATUS, ' and ', prev)):
            pb(prev.right << RESULT, RESULT << staging)
