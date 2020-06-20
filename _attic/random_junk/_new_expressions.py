from contextlib import contextmanager


class Choice(Expr):
    def __init__(self, *exprs):
        self.exprs = [conv(x) for x in exprs]

    def parse(self, text, pos):
        best_failure = None
        for expr in self.exprs:
            result = expr.parse(text, pos)

            # Consume the "is_commit" flag.
            if result.is_success:
                if result.is_commit:
                    return Success(result.value, result.pos, is_commit=False)
                else:
                    return result

            # Consume the "is_abort" flag.
            if result.is_abort:
                return Failure(result.expr, result.pos, is_abort=False)

            # Keep track of the failure that consumed the most input.
            if best_failure is None or best_failure.pos < result.pos:
                best_failure = result

        return best_failure if best_failure is not None else Failure(self, pos)

    def compile(self, compiler, pos):
        result = compiler.new_result("choice")
        for expr in self.exprs:
            item = expr.compile(compiler, pos)
            with compiler.if_success(item) as branch:
                branch.succeed(result, item.value, item.pos)
            with compiler.or_else() as branch:
                compiler = branch
        branch.fail(result, pos)
        return result


class Seq(Expr):
    def __init__(self, *exprs):
        self.exprs = [conv(x) for x in exprs]

    def parse(self, text, pos):
        result = []
        saw_commit = False
        for expr in self.exprs:
            item = expr.parse(text, pos)
            if not item.is_success:
                return item.abort() if saw_commit else item
            if not saw_commit and item.is_commit:
                saw_commit = True
            result.append(item.value)
            pos = item.pos
        return Success(result, pos, is_commit=saw_commit)

    def compile(self, compiler, pos):
        result = compiler.new_result("seq")
        buf = compiler.new_list("buf")
        for expr in self.exprs:
            item = expr.compile(compiler, pos)
            with compiler.if_failure(item) as branch:
                branch.fail(result, pos)

            with compiler.or_else() as branch:
                branch.append(buf, item.value)
                branch.update_pos(pos, item.pos)
                compiler = branch

        compiler.succeed(result, seq, pos)
        return result


class Compiler:
    def __init__(self):
        pass

    @contextmanager
    def if_failure(self, result):
        pass

    def new_list(self, prefix):
        pass

    def new_result(self, prefix):
        pass
