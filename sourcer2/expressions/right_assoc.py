
class RightAssoc(OperatorPrecedenceRule):
    associativity = 'right'
    num_blocks = 4

    def _compile(self, pb):
        backup = pb.var('backup', Val(None))
        prev = pb.var('prev', Val(None))

        staging = pb.var('staging')
        checkpoint = pb.var('checkpoint')

        with pb.loop():
            with _if_fails(pb, self.operand):
                with pb.IF(prev):
                    with pb.IF(backup):
                        pb(backup.right << prev.left, RESULT << staging)
                    with pb.ELSE():
                        pb(RESULT << prev.left)
                    pb(STATUS << Val(True), POS << checkpoint)
                pb(BREAK)

            pb(checkpoint << POS)
            operand = pb.var('operand', RESULT)

            with _if_fails(pb, self.operators):
                with pb.IF(prev):
                    pb(prev.right << operand, RESULT << staging)

                with pb.ELSE():
                    pb(RESULT << operand)

                pb(STATUS << Val(True), POS << checkpoint, BREAK)

            step = code.Infix(operand, RESULT, Val(None))

            with pb.IF(prev):
                pb(backup << prev, backup.right << prev << step)

            with pb.ELSE():
                pb(staging << prev << step)
