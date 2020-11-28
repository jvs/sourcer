from collections import defaultdict
from contextlib import contextmanager
import io
import textwrap


__version__ = '0.0.1'

__all__ = ['CodeBuilder', 'Code', 'Val', 'Yield']

OMITTED = object()


class CodeBuilder:
    def __init__(self):
        self.state = {}
        self._root = []
        self._statements = self._root
        self._num_blocks = 1
        self._max_num_blocks = 19
        self._names = defaultdict(int)
        self._global_constants = {}

    def __iadd__(self, statement):
        return self.append(statement)

    def write_source(self):
        writer = _Writer()
        for statement in self._statements:
            writer.write_line(statement)
        return writer.getvalue()

    def append(self, statement):
        self._statements.append(statement)
        return self

    def extend(self, statements):
        self._statements.extend(statements)
        return self

    def append_global(self, statement):
        self._root.append(statement)

    def has_available_blocks(self, num_blocks):
        return self._num_blocks + num_blocks <= self._max_num_blocks

    def var(self, base_name, initializer=OMITTED):
        result = self._reserve_name(base_name)
        if initializer is not OMITTED:
            self.append(result << initializer)
        return result

    def _reserve_name(self, base_name):
        self._names[base_name] += 1
        return Code(f'{base_name}{self._names[base_name]}')

    def add_comment(self, content):
        if '\n' not in content:
            ready = '# ' + content
        else:
            safe = content.replace('\\', '\\\\') .replace('"""', '\\"\\"\\"')
            indent = '    ' * (self._num_blocks - 1)
            body = textwrap.indent(safe, indent)
            ready = f'"""\n{body}\n{indent}"""'
        self.append(Code(ready))

    def add_newline(self):
        self.append('')

    @contextmanager
    def CLASS(self, name, superclass=None):
        with self._new_block() as body:
            yield
        extra = f'({superclass})' if superclass else ''
        self.append(Code('class ', name, extra, ':'))
        self.append(_Block(body))
        self.add_newline()

    @contextmanager
    def DEF(self, name, params):
        with self._new_block() as body:
            yield
        self.append(Code('def ', name, '(', ', '.join(params), '):'))
        self.append(_Block(body))
        self.add_newline()

    def WHILE(self, condition):
        return self._control_block('while', condition)

    def IF(self, condition):
        return self._control_block('if', condition)

    def IF_NOT(self, condition):
        return self.IF(Code('not ', Val(condition)))

    @contextmanager
    def ELSE(self):
        with self._new_block() as else_body:
            yield
        self.append('else:')
        self.append(_Block(else_body))

    def FOR(self, item, in_):
        expr = Code(Val(item), ' in ', Val(in_))
        return self._control_block('for', expr)

    def RETURN(self, obj):
        return self.append(Code('return ', Val(obj)))

    def YIELD(self, obj):
        return self.append(Code('yield ', Val(obj)))

    @contextmanager
    def global_section(self):
        saved = self._statements, self._num_blocks
        self._statements = self._root
        self._num_blocks = 1
        try:
            yield
        finally:
            self._statements, self._num_blocks = saved

    @contextmanager
    def _control_block(self, keyword, condition):
        with self._new_block() as body:
            yield
        self.append(Code(keyword, ' ', Val(condition), ':'))
        self.append(_Block(body))

    @contextmanager
    def _new_block(self):
        with self._sandbox() as new_buffer:
            self._num_blocks += 1
            try:
                yield new_buffer
            finally:
                self._num_blocks -= 1

    @contextmanager
    def _sandbox(self):
        saved = self._statements
        self._statements = []
        try:
            yield self._statements
        finally:
            self._statements = saved


class Code:
    def __init__(self, *parts):
        self._parts = parts

    def _write(self, writer):
        for part in self._parts:
            writer.write(part)

    def __repr__(self):
        writer = _Writer()
        self._write(writer)
        return writer.getvalue()

    def __lshift__(self, other):
        return Code(self, ' = ', Val(other))

    def __rlshift__(self, other):
        return Code(Val(other), ' = ', self)

    def __call__(self, *args, **kwargs):
        parts = [self, '(']

        for arg in args:
            parts.extend([Val(arg), ', '])

        for key, value in kwargs.items():
            parts.extend([key, '=', Val(value), ', '])

        # Remove a trailing comma.
        if args or kwargs:
            parts.pop()

        parts.append(')')
        return Code(*parts)

    def __getitem__(self, key):
        return Code(self, '[', Val(key), ']')

    def __getattr__(self, name):
        return Code(self, '.', name)

    def __neg__(self):
        return Code('(-', self, ')')

    def __pos__(self):
        return Code('(+', self, ')')

    def __invert__(self):
        return Code('(~', self, ')')

    def __abs__(self):
        return Code('abs(', self, ')')

    def __eq__(self, other):
        return _binop(self, '==', other)

    def __ne__(self, other):
        return _binop(self, '!=', other)

    def __add__(self, other):
        return _binop(self, '+', other)

    def __radd__(self, other):
        return _binop(other, '+', self)

    def __sub__(self, other):
        return _binop(self, '-', other)

    def __rsub__(self, other):
        return _binop(other, '-', self)

    def __mul__(self, other):
        return _binop(self, '*', other)

    def __rmul__(self, other):
        return _binop(other, '*', self)

    def __matmul__(self, other):
        return _binop(self, '@', other)

    def __rmatmul__(self, other):
        return _binop(other, '@', self)

    def __truediv__(self, other):
        return _binop(self, '/', other)

    def __rtruediv__(self, other):
        return _binop(other, '/', self)

    def __floordiv__(self, other):
        return _binop(self, '//', other)

    def __rfloordiv__(self, other):
        return _binop(other, '//', self)

    def __mod__(self, other):
        return _binop(self, '%', other)

    def __rmod__(self, other):
        return _binop(other, '%', self)

    def __pow__(self, other):
        return _binop(self, '**', other)

    def __rpow__(self, other):
        return _binop(other, '**', self)

    def __and__(self, other):
        return _binop(self, '&', other)

    def __rand__(self, other):
        return _binop(other, '&', self)

    def __or__(self, other):
        return _binop(self, '|', other)

    def __ror__(self, other):
        return _binop(other, '|', self)

    def __xor__(self, other):
        return _binop(self, '^', other)

    def __rxor__(self, other):
        return _binop(other, '^', self)

    def __gt__(self, other):
        return _binop(self, '>', other)

    def __ge__(self, other):
        return _binop(self, '>=', other)

    def __lt__(self, other):
        return _binop(self, '<', other)

    def __le__(self, other):
        return _binop(self, '<=', other)

    def __rshift__(self, other):
        return _binop(self, '>>', other)

    def __rrshift__(self, other):
        return _binop(other, '>>', self)


def Val(obj):
    return obj if isinstance(obj, Code) else Code(repr(obj))


def Yield(obj):
    return Code('(yield ', Val(obj), ')')


class _Block:
    def __init__(self, statements):
        if not isinstance(statements, (list, tuple)):
            raise TypeError('Expected list of tuple')
        self._statements = statements or ['pass']

    def _write_block(self, writer):
        with writer.indented():
            for statement in self._statements:
                writer.write_line(statement)


def _binop(a, op, b):
    assert isinstance(op, str)
    return Code('(', Val(a), f' {op} ', Val(b), ')')


class _Writer:
    def __init__(self):
        self._indent = 0
        self._out = io.StringIO()

    def getvalue(self):
        return self._out.getvalue()

    @contextmanager
    def indented(self):
        was = self._indent
        self._indent += 1
        try:
            yield
        finally:
            self._indent = was

    def write_line(self, obj):
        if isinstance(obj, _Block):
            obj._write_block(self)
        elif isinstance(obj, str) and obj == '':
            self.write('\n')
        else:
            self.write('    ' * self._indent)
            self.write(obj)
            self.write('\n')

    def write(self, obj):
        if hasattr(obj, '_write'):
            obj._write(self)
        else:
            self._out.write(str(obj))
