from collections import namedtuple
import contextlib
import io
import types


def compile_rules(start, rules):
    out = ProgramBuilder()
    return out.run(start, rules)


Target = namedtuple('Target', 'mode, value, pos')


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
        self.set_result(target, mode=False, value=id(expr), pos=pos)

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

    def set(self, target, value):
        self(f'{target} = {value}')

    def set_result(self, target, mode, value, pos):
        self.set(target.mode, mode)
        self.set(target.value, value)
        self.set(target.pos, pos)

    def succeed(self, target, value, pos):
        self.set_result(target, mode=True, value=value, pos=pos)

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

