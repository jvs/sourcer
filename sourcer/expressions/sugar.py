from .discard import Discard
from .list import List


def Left(expr1, expr2):
    return Discard(expr1, expr2, discard_left=False)


def Right(expr1, expr2):
    return Discard(expr1, expr2, discard_left=True)


def Some(expr):
    return List(expr, min_len=1)
