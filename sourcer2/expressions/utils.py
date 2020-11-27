from contextlib import contextmanager

from outsourcer import Code, Yield

from .constants import BREAK, CALL, POS, RESULT, STATUS, TEXT


class SymbolCounter:
    def __init__(self):
        self._symbol_counts = defaultdict(int)

    def previsit(self, node):
        if node.has_name:
            self._symbol_counts[node.name] += 1

        if node.has_params and node.params:
            for param in node.params:
                self._symbol_counts[param] += 1

    def postvisit(self, node):
        if node.has_name:
            self._symbol_counts[node.name] -= 1

        if node.has_params and node.params:
            for param in node.params:
                self._symbol_counts[param] -= 1

    def is_bound(self, ref):
        return self._symbol_counts[ref.name] > 0


def error_func_name(expr):
    return f'_raise_error{expr.program_id}'


def functionalize(out, expr, is_generator=False):
    name = f'_parse_function_{expr.program_id}'
    params = [str(TEXT), str(POS)] + list(sorted(_freevars(expr)))

    with out.global_function(name, params):
        expr._compile(out)
        method = out.YIELD if is_generator else out.RETURN
        method((STATUS, RESULT, POS))
    return Code(name), [Code(x) for x in params]


@contextmanager
def if_succeeds(out, expr):
    expr.compile(out)
    if expr.always_succeeds():
        yield
    else:
        with out.IF(STATUS):
            yield


@contextmanager
def if_fails(out, expr):
    expr.compile(out)
    if expr.always_succeeds():
        with out._sandbox():
            yield
    else:
        with out.IF_NOT(STATUS):
            yield


@contextmanager
def breakable(out):
    with out.WHILE(True):
        yield
        out += BREAK


def infix_str(expr1, op, expr2):
    arg1 = expr1._operand_string()
    arg2 = expr2._operand_string()
    return f'{arg1} {op} {arg2}'


def skip_ignored(pos):
    return Yield((CALL, Code(implementation_name('_ignored')), pos))[2]


def implementation_name(name):
    return f'_try_{name}'


def _freevars(expr):
    result = set()
    counter = SymbolCounter()

    def previsit(node):
        counter.previsit(node)
        # TODO: This needs to be a property or a method. Remove isinstance here.
        if isinstance(node, Ref) and not counter.is_bound(node) and node.is_local:
            result.add(node.name)

    visit(previsit, expr, counter.postvisit)
    return result
