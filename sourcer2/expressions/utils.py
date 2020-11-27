from contextlib import contextmanager
from outsourcer import Code, Yield
from .constants import BREAK, CALL, STATUS


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
    arg1 = expr1.operand_string()
    arg2 = expr2.operand_string()
    return f'{arg1} {op} {arg2}'


def skip_ignored(pos):
    return Yield((CALL, Code(implementation_name('_ignored')), pos))[2]


def implementation_name(name):
    return f'_try_{name}'
