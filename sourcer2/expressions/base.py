from outsourcer import Code

from .constants import STATUS, RESULT, POS
class Expression:
    has_name = False
    has_params = False

    is_commented = True
    is_tagged = True

    def always_succeeds(self):
        return False

    def can_partially_succeed(self):
        # By default, assume that if you don't always succeed, then you can
        # partially succeed.
        return not self.always_succeeds()

    def compile(self, out):
        if not out.has_available_blocks(self.num_blocks):
            func, params = functionalize(out, self, is_generator=False)
            out += (STATUS, RESULT, POS) << func(*params)
            return

        if self.is_tagged:
            out.add_comment(f'Begin {self.__class__.__name__}')

        if self.is_commented:
            out.add_comment(str(self))

        self._compile(out)

        if self.is_tagged:
            out.add_comment(f'End {self.__class__.__name__}')

    def _error_func(self):
        return Code(f'_raise_error{self.program_id}')

    def _operand_string(self):
        return str(self)

    def _argumentize(self, out):
        func, params = functionalize(out, self, is_generator=True)
        if len(params) <= 2:
            return func

        _ParseFunction = Code('_ParseFunction')
        args = tuple(params[2:])
        value = _ParseFunction(func, args, ())
        return out.var('arg', value)

    def _functionalize(self, out):
        pass

    def _freevars(self):
        pass


def visit(expr, previsitor, postvisitor=None):
    if isinstance(expr, Expression):
        previsitor(expr)

        for child in expr.__dict__.values():
            visit(child, previsitor, postvisitor)

        if postvisitor:
            postvisitor(expr)

    elif isinstance(expr, (list, tuple)):
        for child in expr:
            visit(child, previsitor, postvisitor)
