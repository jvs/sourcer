from .expressions import conv


class Call:
    def __init__(self, func, args):
        self.func = func
        self.args = args

    def __repr__(self):
        return f'Call({self.func!r}, {self.args!r})'


class Rule:
    def __init__(self, name, expr):
        self.name = name
        self.expr = conv(expr)

    def __repr__(self):
        return f'Rule({self.name!r}, {self.expr!r})'


class Template:
    def __init__(self, name, params, expr):
        self.name = name
        self.params = params
        self.expr = expr

    def __repr__(self):
        return f'Template({self.name!r}, {self.params!r}, {self.expr!r})'
