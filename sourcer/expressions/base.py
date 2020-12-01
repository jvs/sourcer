from collections import defaultdict
from outsourcer import Code
from .constants import POS, RESULT, STATUS, TEXT


class Expression:
    defines_local = False
    has_params = False

    is_commented = True
    is_reference = False
    is_tagged = True

    def always_succeeds(self):
        return False

    def can_partially_succeed(self):
        # By default, assume that if you don't always succeed, then you can
        # partially succeed.
        return not self.always_succeeds()

    def precompile(self, out):
        pass

    def compile(self, out):
        if not out.has_available_blocks(self.num_blocks):
            func, params = self.functionalize(out, is_generator=False)
            out += (STATUS, RESULT, POS) << func(*params)
            return

        if self.is_tagged:
            out.add_comment(f'Begin {self.__class__.__name__}')

        if self.is_commented:
            out.add_comment(str(self))

        self._compile(out)

        if self.is_tagged:
            out.add_comment(f'End {self.__class__.__name__}')

    def error_func(self):
        return Code(f'_raise_error{self.program_id}')

    def operand_string(self):
        return str(self)

    def argumentize(self, out):
        func, params = self.functionalize(out, is_generator=True)
        if len(params) <= 2:
            return func
        else:
            _ParseFunction = Code('_ParseFunction')
            value = _ParseFunction(func, tuple(params[2:]), ())
            return out.var('arg', value)

    def functionalize(self, out, is_generator=False):
        name = f'_parse_function_{self.program_id}'
        params = [str(TEXT), str(POS)] + list(sorted(self.freevars()))

        with out.global_section():
            with out.DEF(name, params):
                self.compile(out)
                method = out.YIELD if is_generator else out.RETURN
                method((STATUS, RESULT, POS))

        return Code(name), [Code(x) for x in params]

    def freevars(self):
        counter = SymbolCounter()
        visit(self, counter.previsit, counter.postvisit)
        return counter.freevars


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


class SymbolCounter:
    def __init__(self):
        self.freevars = set()
        self._counts = defaultdict(int)

    def previsit(self, node):
        if node.defines_local:
            self._counts[node.name] += 1

        if node.has_params and node.params:
            for param in node.params:
                self._counts[param] += 1

        if node.is_reference and node.is_local and not self.is_bound(node.name):
            self.freevars.add(node.name)

    def postvisit(self, node):
        if node.defines_local:
            self._counts[node.name] -= 1

        if node.has_params and node.params:
            for param in node.params:
                self._counts[param] -= 1

    def is_bound(self, name):
        return self._counts[name] > 0
