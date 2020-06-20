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


def run(text, pos=0):
    memo = {}
    result = None

    start = $start
    key = (2, start, pos)
    gtor = start(text, pos)
    stack = [(key, gtor)]

    while stack:
        key, gtor = stack[-1]
        result = gtor.send(result)

        if result[0] != 2:
            stack.pop()
            memo[key] = result
        elif result in memo:
            result = memo[key]
        else:
            gtor = result[1](text, result[2])
            stack.append((result, gtor))
            result = None

    if result[0]:
        return result[1]
    else:
        raise ParseError(*result)
'''


Target = namedtuple('Target', 'mode, value, pos')


class Choice:
    def __init__(self, *exprs):
        self.exprs = [conv(x) for x in exprs]

    def _compile(self, out, target):
        items = []
        for expr in self.exprs:
            item = out.compile(expr)
            items.append(item)
            with out.IF(f'{out.is_success(item)} or {out.is_error(item)}'):
                out.copy_result(target, item)
            out('else:')
            out.indent += 1

        out.fail(target, self, 'pos')
        for item in items:
            with out.IF(f'{target.pos} < {item.pos}'):
                out.copy_result(target, item)


class Drop:
    def __init__(self, expr1, expr2, drop_left=True):
        self.expr1 = conv(expr1)
        self.expr2 = conv(expr2)

    def _compile(self, out, target):
        item1 = out.compile(self.expr1)

        with out.IF_NOT(out.is_success(item1)):
            out.copy_result(target, item1)

        with out.ELSE():
            out(f'pos = {item1.pos}')
            item2 = out.compile(self.expr2)

            if self.drop_left:
                out.copy_result(target, item2)
            else:
                with out.IF(out.is_success(item2)):
                    out.succeed(target, item1.value, item2.pos)
                with out.ELSE():
                    out.copy_result(target, item2)


def Left(expr1, expr2):
    return Drop(expr1, expr2, drop_left=False)


class List:
    def __init__(self, expr, min_length=0):
        self.expr = conv(expr)
        self.min_length = min_length

    def _compile(self, out, target):
        buf = out.define('buf', '[]')
        out('while True:')
        with out.indented():
            item = out.compile(expr)

            with out.IF(out.is_error(item)):
                out.copy_result(target, item)

            with out.IF_NOT(out.is_success(item)):
                out('break')

            condition = (
                f'not isinstance({item.value}, Token) or '
                f'not {item.value}._is_ignored'
            )
            with out.IF(condition):
                out(f'{buf}.append({item.value})')

            out(f'pos = {item.pos}')

        if min_length > 0:
            with out.IF(f'len({buf}) < min_length'):
                out.fail(target, self, 'pos')
            out('else:')
            out.indent += 1

        out.succeed(target, buf, 'pos')


class Literal:
    def __init__(self, value):
        self.value = value

    def _compile(self, out, target):
        value = out.define('value', repr(self.value))
        with out.IF('isinstance(text, str)'):
            self._compile_for_text(out, target, value)
        with out.ELSE():
            self._compile_for_items(out, target, value)

    def _compile_for_text(self, out, target, value):
        if not isinstance(self.value, str):
            out.fail(target, self, 'pos')
            return
        end = out.define('end', f'pos + {len(self.value)}')
        with out.IF(f'text[pos:{end}] == {value}'):
            out.succeed(target, value, end)
        with out.ELSE():
            out.fail(target, self, 'pos')

    def _compile_for_items(self, out, target, value):
        with out.IF(f'pos < len(text) and text[pos] == {value}'):
            out.succeed(target, value, 'pos + 1')
        with out.ELSE():
            out.fail(target, self, 'pos')


class Opt:
    def __init__(self, expr):
        self.expr = conv(expr)

    def _compile(self, out, target):
        item = out.compile(self.expr)
        with out.IF(f'{out.is_success(item)} or {out.is_error(item)}'):
            out.copy_result(target, item)
        with out.ELSE():
            out.succeed(target, 'None', 'pos')


class Ref:
    def __init__(self, rule_name):
        self.rule_name = rule_name

    def _compile(self, out, target):
        rule = out.rule_map[self.rule_name]
        out(f'{target.mode}, {target.value}, {target.pos} = yield (2, {rule}, pos)')


class Regex:
    def __init__(self, pattern):
        if isinstance(pattern, str):
            pattern = re.compile(pattern)
        elif not isinstance(pattern, typing.Pattern):
            raise TypeError('Expected Pattern object')
        self.pattern = pattern

    def _compile(self, out, target):
        pattern = out.define_global('pattern', repr(self.pattern))

        with out.IF('isinstance(text, str)'):
            match = out.define('match', f'{pattern}.match(text, pos)')

            with out.IF(match):
                out.succeed(target, f'{match}.group(0)', f'{match}.end()')

            with out.ELSE():
                out.fail(target, self, 'pos')

        with out.ELIF('pos >= len(text)'):
            out.fail(target, self, 'pos')

        with out.ELSE():
            item = out.define('item', 'text[pos]')
            value = out.define('value',
                f'{item}.value if isinstance(item, Token) else item')
            match = out.define('match',
                f'{pattern}.fullmatch({value}) if isinstance({value}, str) else None')
            with out.IF(match):
                out.succeed(target, value, 'pos + 1')
            with out.ELSE():
                out.fail(target, self, 'pos')


def Right(expr1, expr2):
    return Drop(expr1, expr2, drop_left=True)


class Rule:
    def __init__(self, name, expr):
        self.name = name
        self.expr = conv(expr)


class Seq:
    def __init__(self, *exprs, constructor=None):
        self.exprs = [conv(x) for x in exprs]
        self.constructor = constructor

    def _compile(self, out, target):
        items = []
        for expr in self.exprs:
            item = out.compile(expr)
            items.append(item)
            with out.IF_NOT(out.is_success(item)):
                out.copy_result(target, item)
            out('else:')
            out.indent += 1
            out(f'pos = {item.pos}')

        values = ', '.join(x.value for x in items)
        if self.constructor is None:
            value = f'[{values}]'
        else:
            value = f'{self.constructor}({values})'
        out.succeed(target, value, 'pos')


def Some(expr):
    return List(expr, min_length=1)


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

    def define_global(self, basename, value):
        name = self.reserve(basename)
        self.global_defs.write(f'{name} = {value}')
        return name

    def ELIF(self, condition):
        self(f'elif {condition}:')
        return self.indented()

    def ELSE(self):
        self('else:')
        return self.indented()

    def fail(self, target, expr, pos):
        self(f'{target.mode} = False')
        self(f'{target.value} = {id(expr)}')
        self(f'{target.pos} = {pos}')

    def IF(self, condition):
        self(f'if {condition}:')
        return self.indented()

    def IF_NOT(self, condition):
        return self.IF(f'not {condition}')

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
        program_text = self.write_program(start, rules)
        code_object = compile(program_text, '<grammar>', 'exec', optimize=2)
        module = types.ModuleType(start)
        exec(code_object, module.__dict__)
        return module

    def succeed(self, target, value, pos):
        self(f'{target.mode} = True')
        self(f'{target.value} = {value}')
        self(f'{target.pos} = {pos}')

    def write_program(self, start, rules):
        self.buf = io.StringIO()
        self.global_defs = io.StringIO()
        self.indent = 0
        self.names = {'pos', 'text', 'source_code'}
        self.rule_map = {x.name: self.reserve(f'_parse_{x.name}') for x in rules}
        for rule in rules:
            self(f'def {self.rule_map[rule.name]}(text, pos):')
            with self.indented():
                result = self.compile(rule.expr)
                self(f'yield ({result.mode}, {result.value}, {result.pos})')
                self('')
        self(_main_template.replace('$start', self.rule_map[start]))
        self.global_defs.write(self.buf.getvalue())
        return self.global_defs.getvalue()


def conv(obj):
    """Converts a Python object to a parsing expression."""
    if hasattr(obj, '_compile'):
        return obj

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


def compile_rules(start, rules):
    out = ProgramBuilder()
    return out.run(start, rules)




