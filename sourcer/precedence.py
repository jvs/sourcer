from .expressions import *


Operation = namedtuple('Operation', 'left, operator, right')


class LeftAssoc(Struct): pass
class RightAssoc(Struct): pass


# Utility function to create a tuple from a variable number of arguments.
pack_tuple = (lambda *args: args)


def ReduceLeft(left, op, right, transform=pack_tuple):
    expr = (left, Some((op, right)))
    assoc = lambda first, rest: transform(first, *rest)
    xform = lambda pair: reduce(assoc, pair[1], pair[0])
    return Transform(expr, xform)


def ReduceRight(left, op, right, transform=pack_tuple):
    expr = (Some((left, op)), right)
    assoc = lambda prev, next: transform(next[0], next[1], prev)
    xform = lambda pair: reduce(assoc, reversed(pair[0]), pair[1])
    return Transform(expr, xform)


def operator_row(operators, has_left=True, has_right=True, method=ReduceLeft):
    middle = reduce(Or, operators)
    def build(Operand):
        left = Operand if has_left else Return(None)
        right = Operand if has_right else Return(None)
        return method(left, middle, right, Operation)
    return build


def InfixLeft(*operators):
    return operator_row(operators)


def InfixRight(*operators):
    return operator_row(operators, method=ReduceRight)


def Prefix(*operators):
    return operator_row(operators, has_left=False, method=ReduceRight)


def Postfix(*operators):
    return operator_row(operators, has_right=False)


def OperatorPrecedence(*rows):
    return reduce(lambda prev, row: row(prev) | prev, rows)
