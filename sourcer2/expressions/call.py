from outsourcer import Code, Yield

from .base import Expression
from .constants import CALL, POS, RESULT, STATUS


class Call(Expression):
    num_blocks = 0

    def __init__(self, func, args):
        self.func = func
        self.args = args

    def __str__(self):
        args = ', '.join(str(x) for x in self.args)
        return f'{self.func}({args})'

    def _compile(self, out):
        args, kwargs = [], []

        for arg in self.args:
            is_kw = isinstance(arg, KeywordArg)
            expr = arg.expr if is_kw else arg
            value = expr.argumentize(out)

            if is_kw:
                kwargs.append((arg.name, value))
            else:
                args.append(value)

        _ParseFunction = Code('_ParseFunction')
        func = _ParseFunction(Code(self.func.resolved), tuple(args), tuple(kwargs))
        func = out.var('func', func)
        out += (STATUS, RESULT, POS) << Yield((CALL, func, POS))


class KeywordArg:
    def __init__(self, name, expr):
        self.name = name
        self.expr = expr

    def __str__(self):
        return f'{self.name}={self.expr}'
