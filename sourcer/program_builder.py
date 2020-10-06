from collections import defaultdict
from contextlib import contextmanager
import io


class ProgramBuilder:
    def __init__(self, docstring=None):
        self._docstring = docstring
        self._imports = set()
        self._globals = []
        self._global_map = {}
        self._global_sections = []
        self._buffer = []
        self._num_blocks = 1
        self._max_num_blocks = 19
        self._id_counter = 0
        self._num_stack_frames = 0
        self._max_num_stack_frames = 800

    def generate_source_code(self):
        writer = ProgramWriter()

        if self._docstring:
            writer.write_str('"""\n')
            writer.write_str(self._docstring
                .replace('\\', '\\\\')
                .replace('"""', '\\"\\"\\"'))
            writer.write_str('\n"""\n\n')

        for imp in sorted(self._imports):
            writer.write_line(imp)

        writer.write_str('\n\n')

        for stmt in self._buffer:
            writer.write_stmt(stmt)
            writer.write_str('\n')

        writer.write_str('\n')

        for stmt in self._globals:
            writer.write_stmt(stmt)

        writer.write_str('\n\n')

        for section in self._global_sections:
            for stmt in section:
                writer.write_stmt(stmt)
            writer.write_str('\n')

        return writer._out.getvalue()

    def reserve_id(self):
        self._id_counter += 1
        return self._id_counter

    def has_available_blocks(self, num_blocks):
        return self._num_blocks + num_blocks <= self._max_num_blocks

    def add_import(self, import_str):
        self._imports.add(import_str)

    def define_global(self, base_name, initializer):
        assert isinstance(initializer, str)
        if initializer in self._global_map:
            return self._global_map[initializer]
        else:
            var = Var(base_name)
            self._global_map[initializer] = var
            self._globals.append(var << Raw(initializer))
            return var

    def var(self, base_name, initializer=None):
        result = Var(base_name)
        if initializer:
            self(result << initializer)
        return result

    def __call__(self, *stmts):
        self._buffer.extend(stmts)

    @contextmanager
    def _sandbox(self):
        prev = self._buffer
        self._buffer = []
        try:
            yield self._buffer
        finally:
            self._buffer = prev

    @contextmanager
    def _new_block(self):
        with self._sandbox() as new_buffer:
            self._num_blocks += 1
            try:
                yield new_buffer
            finally:
                self._num_blocks -= 1

    @contextmanager
    def IF(self, condition):
        with self._new_block() as then_body:
            yield
        self._buffer.append(IfStmt(condition, then_body))

    def IF_NOT(self, condition):
        return self.IF(Not(condition))

    @contextmanager
    def ELSE(self):
        assert self._buffer and isinstance(self._buffer[-1], IfStmt)
        with self._new_block() as else_body:
            yield
        self._buffer[-1]._else_body = else_body

    @contextmanager
    def breakable(self):
        with self.loop():
            yield
            self._buffer.append(Raw('break'))

    @contextmanager
    def loop(self):
        with self._new_block() as loop_body:
            yield
        self._buffer.append(While(True, loop_body))

    @contextmanager
    def global_function(self, name, params):
        with self.global_section():
            with self.local_function(name, params):
                yield

    @contextmanager
    def local_function(self, name, params):
        with self._sandbox() as func_body:
            yield
        self._buffer.append(FuncStmt(name, params, func_body))

    @contextmanager
    def global_class(self, name, superclass):
        with self.global_section():
            with self._sandbox() as class_body:
                yield
            self._buffer.append(ClassStmt(name, superclass, class_body))

    @contextmanager
    def global_section(self):
        with self._sandbox() as section:
            prev = self._num_blocks
            self._num_blocks = 1
            try:
                yield
            finally:
                self._num_blocks = prev
        self._global_sections.append(section)


class Expr:
    def __call__(self, *a, **k):
        return Call(self, a, k)

    def __eq__(self, other):
        return Binop(self, '==', other)

    def __ne__(self, other):
        return Binop(self, '!=', other)

    def __lshift__(self, other):
        return Assign(self, other)

    def __add__(self, other):
        return Binop(self, '+', other)

    def __getitem__(self, key):
        return GetItem(self, key)

    def __getattr__(self, name):
        return Dot(self, name)

    def __rshift__(self, other):
        return Slice(self, other)

    def __lt__(self, other):
        return Binop(self, '<', other)

    def __le__(self, other):
        return Binop(self, '<=', other)


class Assign(Expr):
    def __init__(self, left, right):
        self._left = left
        self._right = right

    def write(self, writer):
        writer.write_expr(self._left)
        writer.write_str(' = ')
        writer.write_expr(self._right)


class Binop(Expr):
    def __init__(self, left, op, right):
        self._left = left
        self._op = op
        self._right = right

    def write(self, writer):
        writer.write_str('(')
        writer.write_expr(self._left)
        writer.write_str(f' {self._op} ')
        writer.write_expr(self._right)
        writer.write_str(')')


class Call(Expr):
    def __init__(self, func, args, kwargs):
        if not isinstance(kwargs, dict):
            raise TypeError(f'Expected dict. Received: {kwargs!r}')

        if not all(isinstance(x, str) for x in kwargs.keys()):
            raise TypeError(f'Expected str keys. Received: {list(kwargs.keys())}.')

        self._func = func
        self._args = args
        self._kwargs = kwargs

    def write(self, writer):
        writer.write_expr(self._func)
        writer.write_str('(')

        for i, item in enumerate(self._args):
            if i > 0:
                writer.write_str(', ')
            writer.write_expr(item)

        for i, (name, item) in enumerate(self._kwargs):
            if i > 0 or self.args:
                writer.write_str(', ')
            writer.write_str(name + '=')
            writer.write_expr(item)

        writer.write_str(')')


class ClassStmt:
    def __init__(self, name, superclass, body):
        self._name = name
        self._superclass = superclass
        self._body = body

    def write(self, writer):
        writer.write_str(f'class {self._name}')
        writer.write_str(f'({self._superclass}):\n' if self._superclass else ':\n')

        with writer.indented():
            for stmt in self._body:
                if isinstance(stmt, FuncStmt) and stmt._name == '__init__':
                    writer.write_str('\n')
                writer.write_stmt(stmt)


class Dot(Expr):
    def __init__(self, left, name):
        if not isinstance(name, str):
            raise TypeError(f'Expected str. Received: {name!r}.')
        self._left = left
        self._name = name

    def write(self, writer):
        writer.write_expr(self._left)
        writer.write_str('.' + self._name)


class FuncStmt:
    def __init__(self, name, params, body):
        self._name = name
        self._params = params
        self._body = body

    def write(self, writer):
        writer.write_str(f'def {self._name}(')
        writer.write_str(', '.join(self._params))
        writer.write_str('):\n')

        with writer.indented():
            for stmt in self._body:
                writer.write_stmt(stmt)


class GetItem(Expr):
    def __init__(self, left, right):
        self._left = left
        self._right = right

    def write(self, writer):
        writer.write_expr(self._left)
        writer.write_str('[')
        writer.write_expr(self._right)
        writer.write_str(']')


class IfExpr:
    def __init__(self, condition, then_expr, else_expr):
        self._condition = condition
        self._then_expr = then_expr
        self._else_expr = else_expr

    def write(self, writer):
        writer.write_str('(')
        writer.write_expr(self._then_expr)
        writer.write_str(' if ')
        writer.write_expr(self._condition)
        writer.write_str(' else ')
        writer.write_expr(self._else_expr)
        writer.write_str(')')


class IfStmt:
    def __init__(self, condition, then_body, else_body=None):
        self._condition = condition
        self._then_body = then_body
        self._else_body = else_body

    def write(self, writer):
        writer.write_str('if ')
        writer.write_expr(self._condition)
        writer.write_str(':\n')

        with writer.indented():
            for stmt in self._then_body:
                writer.write_stmt(stmt)

        if self._else_body:
            writer.write_line('else:')
            with writer.indented():
                for stmt in self._else_body:
                    writer.write_stmt(stmt)


class LIST(Expr):
    def __init__(self, *items):
        self._items = items

    def write(self, writer):
        writer.write_str('[')
        for i, item in enumerate(self._items):
            if i > 0:
                writer.write_str(', ')
            writer.write_expr(item)
        writer.write_str(']')


class Not(Expr):
    def __init__(self, right):
        self._right = right

    def write(self, writer):
        writer.write_str('(not ')
        writer.write_expr(self._right)
        writer.write_str(')')


class Raise:
    def __init__(self, expr=None):
        self._expr = expr

    def write(self, writer):
        writer.write_str('raise')

        if self._expr is not None:
            writer.write_str(' ')
            writer.write_expr(self._expr)


class Raw(Expr):
    def __init__(self, contents):
        assert isinstance(contents, str)
        self._contents = contents

    def __str__(self):
        return self._contents

    def write(self, writer):
        writer.write_str(self._contents)


class Return:
    def __init__(self, expr=None):
        self._expr = expr

    def write(self, writer):
        writer.write_str('return')

        if self._expr is not None:
            writer.write_str(' ')
            writer.write_expr(self._expr)


class Slice(Expr):
    def __init__(self, left, right):
        self._left = left
        self._right = right

    def write(self, writer):
        writer.write_expr(self._left)
        writer.write_str(' : ')
        writer.write_expr(self._right)


class Tup(Expr):
    def __init__(self, *items):
        self._items = items

    def write(self, writer):
        writer.write_str('(')
        for i, item in enumerate(self._items):
            if i > 0:
                writer.write_str(' ')
            writer.write_expr(item)
            writer.write_str(',')
        writer.write_str(')')


class Val:
    def __init__(self, value):
        self._value = value

    def write(self, writer):
        writer.write_str(repr(self._value))


class Var(Expr):
    def __init__(self, base_name):
        self._base_name = base_name
        self._full_name = None

    def write(self, writer):
        if self._full_name is None:
            self._full_name = writer.generate_unique_name(self._base_name)
        writer.write_str(self._full_name)


class While:
    def __init__(self, condition, loop_body):
        self._condition = condition
        self._loop_body = loop_body

    def write(self, writer):
        writer.write_str('while ')
        writer.write_expr(self._condition)
        writer.write_str(':\n')

        with writer.indented():
            for stmt in self._loop_body:
                writer.write_stmt(stmt)


class Yield(Expr):
    def __init__(self, right):
        self._right = right

    def write(self, writer):
        writer.write_str('(yield ')
        writer.write_expr(self._right)
        writer.write_str(')')


class ProgramWriter:
    def __init__(self):
        self._indent = 0
        self._out = io.StringIO()
        self._names = defaultdict(int)

    def generate_unique_name(self, base_name):
        self._names[base_name] += 1
        return f'{base_name}{self._names[base_name]}'

    @contextmanager
    def indented(self):
        was = self._indent
        self._indent += 1
        try:
            yield
        finally:
            self._indent = was

    def write_expr(self, expr):
        if isinstance(expr, (bool, int, float, str)):
            self.write_str(str(expr))
        elif isinstance(expr, (list, tuple)):
            self.write_str(repr(expr))
        elif hasattr(expr, 'write'):
            expr.write(self)

    def write_indent(self):
        self.write_str('    ' * self._indent)

    def write_line(self, contents):
        self.write_stmt(Raw(contents))

    def write_stmt(self, stmt):
        self.write_indent()
        stmt.write(self)
        if not isinstance(stmt, (IfStmt, While)):
            self.write_str('\n')

    def write_str(self, contents):
        self._out.write(contents)
