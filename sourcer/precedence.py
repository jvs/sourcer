from .terms import *


Operation = namedtuple('Operation', 'left, operator, right')


class LeftAssoc(Struct): pass
class RightAssoc(Struct): pass


# Utility function to create a tuple from a variable number of arguments.
pack_tuple = (lambda *args: args)


def ReduceLeft(left, op, right, transform=pack_tuple):
    term = (left, Some((op, right)))
    assoc = lambda first, rest: transform(first, *rest)
    xform = lambda pair: reduce(assoc, pair[1], pair[0])
    return Transform(term, xform)


def ReduceRight(left, op, right, transform=pack_tuple):
    term = (Some((left, op)), right)
    assoc = lambda prev, next: transform(next[0], next[1], prev)
    xform = lambda pair: reduce(assoc, reversed(pair[0]), pair[1])
    return Transform(term, xform)


class OperatorRow(object):
    has_left = True
    has_right = True
    reduce_left = True

    def __init__(self, *operators):
        self.operator = operators

    def build(self, Operand):
        left = Operand if self.has_left else None
        right = Operand if self.has_right else None
        method = ReduceLeft if self.reduce_left else ReduceRight
        return method(left, Or(*self.operator), right, Operation)


class InfixLeft(OperatorRow): reduce_left = True
class InfixRight(OperatorRow): reduce_left = False


class Prefix(OperatorRow):
    has_left = False
    reduce_left = False


class Postfix(OperatorRow):
    has_right = False
    reduce_left = True


def OperatorPrecedence(*rows):
    ext = lambda Operand, row: row.build(Operand) | Operand
    return reduce(ext, rows)
