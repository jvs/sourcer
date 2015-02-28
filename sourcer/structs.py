from .expressions import *
from .precedence import *


def compile_struct(node, *args):
    fields = _struct_fields(node, *args)
    if issubclass(node, (LeftAssoc, RightAssoc)):
        return _compile_assoc_struct(node, fields)
    else:
        return _compile_simple_struct(node, fields)


def compile_bound_struct(node):
    return lambda x: compile_struct(node, x)


def _compile_assoc_struct(node, fields):
    first = fields[0][-1]
    middle = tuple(p[-1] for p in fields[1:-1])
    last = fields[-1][-1]
    def build(left, op, right):
        values = [left] + list(op) + [right]
        return _build_struct(node, fields, values)
    is_left = issubclass(node, LeftAssoc)
    cls = ReduceLeft if is_left else ReduceRight
    return cls(first, middle, last, build)


def _compile_simple_struct(node, fields):
    raw = tuple(i[1] for i in fields)
    build = lambda values: _build_struct(node, fields, values)
    return Transform(raw, build)


def _build_struct(node, fields, values):
    ans = node.__new__(node)
    for field, value in zip(fields, values):
        setattr(ans, field[0], value)
    return ans


def _struct_fields(cls, *args):
    ans = []
    class AttributeRecorder(cls):
        def __setattr__(self, name, value):
            ans.append((name, value))
            cls.__setattr__(self, name, value)
    recorder = AttributeRecorder.__new__(AttributeRecorder)
    recorder.parse(*args)
    return ans
