
class Postfix(OperatorPrecedenceRule):
    num_blocks = 3

    def _compile(self, pb):
        with _if_succeeds(pb, self.operand):
            staging = pb.var('staging', RESULT)
            checkpoint = pb.var('checkpoint', POS)

            with pb.loop():
                self.operators.compile(pb)

                with pb.IF(STATUS):
                    pb(staging << code.Postfix(staging, RESULT))
                    pb(checkpoint << POS)

                with pb.ELSE():
                    pb(
                        STATUS << Val(True),
                        RESULT << staging,
                        POS << checkpoint,
                        BREAK,
                    )
