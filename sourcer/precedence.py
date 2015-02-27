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


class OperatorRow(object):
    has_left = True
    has_right = True
    reduce_left = True

    def __init__(self, *operators):
        # SHOULD: Clean up this constructor.
        if len(operators) == 0:
            self.operator = Literal(object())
        elif len(operators) == 1:
            self.operator = operators[0]
        else:
            self.operator = reduce(Or, operators)

    def build(self, Operand):
        left = Operand if self.has_left else Return(None)
        right = Operand if self.has_right else Return(None)
        method = ReduceLeft if self.reduce_left else ReduceRight
        return method(left, self.operator, right, Operation)


class InfixLeft(OperatorRow): reduce_left = True
class InfixRight(OperatorRow): reduce_left = False


class Prefix(OperatorRow):
    has_left = False
    reduce_left = False


class Postfix(OperatorRow):
    has_right = False
    reduce_left = True


def OperatorPrecedence(*rows):
    return reduce(lambda prev, row: row.build(prev) | prev, rows)
