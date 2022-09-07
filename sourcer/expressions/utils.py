from contextlib import contextmanager
from outsourcer import Code, Yield
from .constants import BREAK, CALL, POS, STATUS


@contextmanager
def if_succeeds(out, flags, expr):
    expr.compile(out, flags)
    if expr.always_succeeds():
        yield
    else:
        with out.IF(STATUS):
            yield


@contextmanager
def if_fails(out, flags, expr):
    expr.compile(out, flags)
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


@contextmanager
def repeat(out, flags, expr, checkpoint):
    can_partially_succeed = expr.can_partially_succeed()

    with out.WHILE(True):
        if can_partially_succeed:
            out += (checkpoint << POS)

        with if_fails(out, flags, expr):
            if can_partially_succeed:
                out += (POS << checkpoint)
            out += BREAK

        yield


def infix_str(expr1, op, expr2):
    arg1 = expr1.operand_string()
    arg2 = expr2.operand_string()
    return f'{arg1} {op} {arg2}'


def skip_ignored(pos, flags):
    func = implementation_name('_ignored')

    if flags.uses_context:
        func = '_ctx.' + func

    return Yield((CALL, Code(func), pos))[2]


def implementation_name(name):
    return f'_try_{name}'
