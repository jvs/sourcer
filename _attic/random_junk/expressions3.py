from collections import namedtuple
import contextlib
import io
import re
import types
import typing


_main_template = r'''
class ParseError(Exception):
    def __init__(self, mode, expr_code, pos):
        self.is_error = (mode is None)
        self.expr_code = expr_code
        self.pos = pos


def _main(text, pos=0):
    memo = {}
    result = None

    start = $start
    key = (0, start, pos)
    gtor = start(text, pos)
    stack = [(key, gtor)]

    while stack:
        key, gtor = stack[-1]
        result = gtor.send(result)

        if result[0] == 0:
            if result in memo:
                result = memo[key]
            else:
                gtor = result[1](text, result[2])
                stack.append((result, gtor))
                result = None
        else:
            stack.pop()
            memo[key] = result

    if result[0]:
        return result[1]
    else:
        raise ParseError(*result)
'''


Target = namedtuple('Target', 'mode, value, pos')


class Expr:
    pass


class Choice(Expr):
    def __init__(self, *exprs):
        self.exprs = [conv(x) for x in exprs]

    def _compile(self, out, target):
        items = []
        for expr in self.exprs:
            item = out.compile(expr)
            items.append(item)
            out(f'if {out.is_success(item)} or {out.is_error(item)}:')
            with out.indented():
                out.copy_result(target, item)
            out('else:')
            out.indent += 1

        out.fail(target, self, 'pos')
        for item in items:
            out(f'if {target.pos} < {item.pos}:')
            with out.indented():
                out.copy_result(target, item)


class List(Expr):
    def __init__(self, expr, min_length=0):
        self.expr = conv(expr)
        self.min_length = min_length

    def _compile(self, out, target):
        buf = out.define('buf', '[]')
        out('while True:')
        with out.indented():
            item = out.compile(expr)

            out(f'if {out.is_error(item)}:')
            with out.indented():
                out.copy_result(target, item)

            out(f'if not {out.is_success(item)}:')
            with out.indented():
                out('break')

            out(f'if not isinstance({item.value}, Token) or not {item.value}._is_ignored:')
            with out.indented():
                out(f'{buf}.append({item.value})')

            out(f'pos = {item.pos}')

        if min_length > 0:
            out(f'if len({buf}) < min_length:')
            with out.indented():
                out.fail(target, self, 'pos')
            out('else:')
            out.indent += 1

        out.succeed(target, buf, 'pos')


class Literal(Expr):
    def __init__(self, value):
        self.value = value

    def _compile(self, out, target):
        value = out.define('value', repr(self.value))
        out('if isinstance(text, str):')
        with out.indented():
            self._compile_for_text(out, target, value)
        out('else:')
        with out.indented():
            self._compile_for_items(out, target, value)

    def _compile_for_text(self, out, target, value):
        if not isinstance(self.value, str):
            out.fail(target, self, 'pos')
            return
        end = out.define('end', f'pos + {len(self.value)}')
        out(f'if text[pos:{end}] == {value}:')
        with out.indented():
            out.succeed(target, value, end)
        out('else:')
        with out.indented():
            out.fail(target, self, 'pos')

    def _compile_for_items(self, out, target, value):
        out(f'if pos < len(text) and text[pos] == {value}:')
        with out.indented():
            out.succeed(target, value, 'pos + 1')
        out('else:')
        with out.indented():
            out.fail(target, self, 'pos')


class Ref(Expr):
    def __init__(self, rule_name):
        self.rule_name = rule_name

    def _compile(self, out, target):
        rule = out.rule_map[self.rule_name]
        out(f'{target.mode}, {target.value}, {target.pos} = yield (0, {rule}, pos)')


class Rule:
    def __init__(self, name, expr):
        self.name = name
        self.expr = conv(expr)


class Seq(Expr):
    def __init__(self, *exprs):
        self.exprs = [conv(x) for x in exprs]

    def _compile(self, out, target):
        items = []
        for expr in self.exprs:
            item = out.compile(expr)
            items.append(item)
            out(f'if not {out.is_success(item)}:')
            with out.indented():
                out.copy_result(target, item)
            out('else:')
            out.indent += 1
            out(f'pos = {item.pos}')
        values = ', '.join(x.value for x in items)
        out.succeed(target, f'[{values}]', 'pos')


class ProgramBuilder:
    def __call__(self, text):
        self.buf.write('    ' * self.indent)
        self.buf.write(text)
        self.buf.write('\n')

    def copy_result(self, target, result):
        for field in target._fields:
            self(f'{getattr(target, field)} = {getattr(result, field)}')

    def compile(self, expr):
        was = self.indent
        try:
            target = Target(
                mode=self.reserve('mode'),
                value=self.reserve('value'),
                pos=self.reserve('pos'),
            )
            expr._compile(self, target)
            return target
        finally:
            self.indent = was

    def define(self, basename, value):
        name = self.reserve(basename)
        self(f'{name} = {value}')
        return name

    def fail(self, target, expr, pos):
        self(f'{target.mode} = False')
        self(f'{target.value} = {id(expr)}')
        self(f'{target.pos} = {pos}')

    @contextlib.contextmanager
    def indented(self):
        was = self.indent
        self.indent += 1
        try:
            yield
        finally:
            self.indent = was

    def is_error(self, target):
        return f'{target.mode} is None'

    def is_success(self, target):
        return f'{target.mode}'

    def reserve(self, basename):
        count = 1
        while True:
            result = f'{basename}{count}'
            if result not in self.names:
                self.names.add(result)
                return result
            count += 1

    def run(self, start, rules):
        self.buf = io.StringIO()
        self.indent = 0
        self.names = {'pos', 'text'}
        self.rule_map = {x.name: self.reserve(f'_parse_{x.name}') for x in rules}
        for rule in rules:
            self(f'def {self.rule_map[rule.name]}(text, pos):')
            with self.indented():
                result = self.compile(rule.expr)
                self(f'yield ({result.mode}, {result.value}, {result.pos})')
                self('')
        self(f'def _main(text, pos=0):')
        return self.buf.getvalue()

    def succeed(self, target, value, pos):
        self(f'{target.mode} = True')
        self(f'{target.value} = {value}')
        self(f'{target.pos} = {pos}')


def conv(obj):
    """Converts a Python object to a parsing expression."""
    if isinstance(obj, Expr):
        return obj

    if isinstance(obj, list) and len(obj) == 1:
        return List(obj)

    if isinstance(obj, (list, tuple)):
        return Seq(*obj)

    if isinstance(obj, types.LambdaType):
        if not hasattr(obj, '_parsing_expression'):
            obj._parsing_expression = Lazy(obj)
        return obj._parsing_expression

    if isinstance(obj, typing.Pattern):
        return Regex(obj)
    else:
        return Literal(obj)
