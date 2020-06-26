from collections import namedtuple
from string import Template
import contextlib
import io
import types

from . import expressions


def compile_statements(statements):
    out = ProgramBuilder()
    return out.run(statements)


Target = namedtuple('Target', 'mode, value, pos')


class ProgramBuilder:
    SUCCESS = 1
    IGNORE = 2
    CONTINUE = 3
    FAILURE = False
    ERROR = None

    def __call__(self, text):
        self.buf.write('    ' * self.indent)
        self.buf.write(text)
        self.buf.write('\n')

    def add_import(self, path):
        self.imports.add(path)

    def apply_templates(self, statements):
        env = {x.name: x for x in statements if isinstance(x, expressions.Template)}
        return [x._eval(env) for x in statements]

    def copy_result(self, target, result):
        for field in target._fields:
            self.set(getattr(target, field), getattr(result, field))

    def compile(self, expr, target=None):
        was = self.indent
        if target is None:
            target = Target(
                mode=self.reserve('mode'),
                value=self.reserve('value'),
                pos=self.reserve('pos'),
            )
        try:
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
        self.global_defs.write(f'{name} = {value}\n')
        return name

    def ELIF(self, condition):
        self(f'elif {condition}:')
        return self.indented()

    def ELSE(self):
        self('else:')
        return self.indented()

    def fail(self, target, expr, pos):
        self.set_result(target, mode=self.FAILURE, value=id(expr), pos=pos)

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
        return f'{target.mode} is {self.ERROR}'

    def is_failure(self, target):
        return f'{target.mode} == {self.FAILURE}'

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

    def run(self, statements):
        statements = self.apply_templates(statements)
        program_text = self.write_program(statements)
        return program_text
        # return self.compile_program(program_text)

    def compile_program(self, program_text):
        code_object = compile(program_text, '<grammar>', 'exec', optimize=2)
        # TODO: pick a good name for the module.
        module = types.ModuleType('grammar')
        exec(code_object, module.__dict__)
        return module

    def set(self, target, value):
        self(f'{target} = {value}')

    def set_result(self, target, mode, value, pos):
        self.set(target.mode, mode)
        self.set(target.value, value)
        self.set(target.pos, pos)

    def succeed(self, target, value, pos):
        self.set_result(target, mode=self.SUCCESS, value=value, pos=pos)

    def write_rule_function(self, name, expr):
        self(f'def {name}(text, pos):')
        with self.indented():
            result = self.compile(expr)
            self(f'yield ({result.mode}, {result.value}, {result.pos})')
            self('')

    def write_program(self, statements):
        tokens = [x for x in statements if isinstance(x, expressions.Token)]
        rules = [x for x in statements if not isinstance(x, expressions.Template)]
        start = None

        for x in rules:
            if x.name.lower() == 'start':
                start = x.name

        if start is None:
            names = sorted(x.name for x in rules)
            raise Exception(f'Expected "start" rule. Received: {names}')

        self.buf = io.StringIO()
        self.imports = set()
        self.global_defs = io.StringIO()
        self.indent = 0
        self.names = {'pos', 'start', 'source_code', 'text'}
        self.env = {x.name: x for x in statements if isinstance(x, expressions.Template)}
        self.rule_map = {x.name: self.reserve(f'_parse_{x.name}') for x in rules}

        if tokens:
            self.write_tokenizer(tokens)
            tokenize_step = 'text = _run(text, pos, _tokenize)'
            reset_pos = 'pos = 0'
        else:
            tokenize_step = ''
            reset_pos = ''

        for rule in rules:
            self.write_rule_function(self.rule_map[rule.name], rule.expr)

        result = io.StringIO()
        for imp in self.imports:
            result.write('import ')
            result.write(imp)
            result.write('\n')
        result.write(self.global_defs.getvalue())
        result.write(_main_template.substitute(
            CONTINUE=self.CONTINUE,
            reset_pos=reset_pos,
            start=self.rule_map[start],
            tokenize_step=tokenize_step,
        ))
        result.write(self.buf.getvalue())
        return result.getvalue()

    def write_tokenizer(self, tokens):
        # TODO: Either do `Left(delegate, End)` or add a catch-all error token.
        delegate = expressions.List(expressions.Choice(*(TokenWrapper(x) for x in tokens)))
        self.write_rule_function('_tokenize', delegate)


class TokenWrapper:
    def __init__(self, token_expr):
        self.token_expr = token_expr

    def _compile(self, out, target):
        return self.token_expr._compile_for_text(out, target)


_main_template = Template(r'''
class ParseError(Exception):
    def __init__(self, mode, expr_code, pos):
        self.is_error = (mode is None)
        self.expr_code = expr_code
        self.pos = pos


class Node:
    pass


class Token(Node):
    def __init__(self, value):
        self.value = value


class Infix(Node):
    def __init__(self, left, operator, right):
        self.left = left
        self.operator = operator
        self.right = right


class Postfix(Node):
    def __init__(self, left, operator):
        self.left = left
        self.operator = operator


class Prefix(Node):
    def __init__(self, operator, right):
        self.operator = operator
        self.right = right


def parse(text, pos=0):
    $tokenize_step
    $reset_pos
    return _run(text, pos, $start)


def _run(text, pos, start):
    memo = {}
    result = None

    key = ($CONTINUE, start, pos)
    gtor = start(text, pos)
    stack = [(key, gtor)]

    while stack:
        key, gtor = stack[-1]
        result = gtor.send(result)

        if result[0] != $CONTINUE:
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
''')
