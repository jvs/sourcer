from string import Template

from outsourcer import CodeBuilder, Code, Val

from . import expressions as ex
from .expressions import (
    TEXT, POS, Choice, Class, Ref, Right, Rule, Skip, visit
)


def generate_source_code(docstring, nodes):
    out = CodeBuilder()
    out.add_docstring(docstring)
    out += Code(_program_setup)

    # Collect all the rules and stuff.
    rules, ignored = [], []
    start_rule = None

    for node in nodes:
        # Just add Python sections directly to the program.
        if isinstance(node, (ex.PythonExpression, ex.PythonSection)):
            out += Code(node.source_code)
            continue

        rules.append(node)

        if node.is_ignored:
            ignored.append(node)

        if start_rule is None and node.name and node.name.lower() == 'start':
            start_rule = node

    if start_rule is not None and start_rule.is_ignored:
        raise Exception(
            f'The {start_rule!r} rule may not have the "ignored" modifier.'
        )

    if not rules:
        raise Exception('Expected one or more grammar rules.')

    visited_names = set()
    for rule in rules:
        if rule.name is not None and rule.name.startswith('_'):
            raise Exception(
                'Grammar rule names must start with a letter. Found a rule that'
                f' starts with an underscore: "{rule.name}". '
            )

        if not rule.name:
            rule.name = f'_anonymous_{id(rule)}'

        if rule.name in visited_names:
            raise Exception(
                'Each grammar rule must have a unique name. Found two or more'
                f' rules named "{rule.name}".'
            )
        visited_names.add(rule.name)

    if ignored:
        # Create a rule called "_ignored" that skips all the ignored rules.
        refs = [Ref(x.name) for x in ignored]
        rules.append(Rule('_ignored', None, Skip(*refs), 'ignored'))

        # If we have a start rule, then update its expression to skip ahead past
        # any leading ignored stuff.
        if isinstance(start_rule, Class):
            first_rule = start_rule.fields[0] if start_rule.fields else None
        else:
            first_rule = start_rule

        if first_rule:
            assert isinstance(first_rule, Rule)
            impl_name = ex.implementation_name('_ignored')
            first_rule.expr = Right(Ref(impl_name), first_rule.expr)

        # Update the "skip_ignored" flag of each StringLiteral and RegexLiteral.
        def _set_skip_ignored(expr):
            if hasattr(expr, 'skip_ignored'):
                expr.skip_ignored = True

        for rule in rules:
            if not rule.is_ignored:
                visit(rules, _set_skip_ignored)

    _assign_ids(rules)
    _update_local_references(rules)
    _update_rule_references(rules)

    default_rule = start_rule or rules[0]

    out += Code(Template(_main_template).substitute(
        CALL=ex.CALL,
        start=ex.implementation_name(default_rule.name),
    ))

    error_delegates = {}
    def set_error_delegate(expr):
        if not isinstance(expr, Choice):
            return
        real, fail = [], []
        for option in expr.exprs:
            if isinstance(option, ex.Fail):
                fail.append(option)
            else:
                real.append(option)
        if not real or not fail:
            return
        delegate = Choice(*real)
        error_delegates[fail[-1].program_id] = Choice(*real)

    for rule in rules:
        visit(rule, set_error_delegate)

    visited = set()
    def maybe_compile_error_message(out, rule, expr):
        if not hasattr(expr, 'complain') or expr.program_id in visited:
            return

        visited.add(expr.program_id)
        if expr.always_succeeds():
            return

        with out.global_section():
            TITLE, LINE, COL = Code('title'), Code('line'), Code('col')

            with out.DEF(str(expr.error_func()), [str(TEXT), str(POS)]):
                with out.IF(Code('len')(TEXT) <= POS):
                    out += TITLE << 'Unexpected end of input.'
                    out += LINE << None
                    out += COL << None

                with out.ELSE():
                    out += (LINE, COL) << Code('_get_line_and_column')(TEXT, POS)
                    out += Code('excerpt') << Code('_extract_excerpt')(TEXT, POS, COL)
                    out += TITLE << Code(
                        r"f'Error on line {line}, column {col}:\n{excerpt}\n'"
                    )

                delegate = error_delegates.get(expr.program_id, expr)
                out.extend([
                    Code('details = ('),
                    Val(f'Failed to parse the {rule.name!r} rule, at the expression:\n'),
                    Val(f'    {str(delegate)}\n\n'),
                    Val(expr.complain()),
                    Code(')'),
                    Code('raise ParseError', (TITLE + Code('details'), POS, LINE, COL)),
                ])

    for rule in rules:
        visit(rule, lambda x: x.precompile(out))

    out.add_newline()

    for rule in rules:
        rule.compile(out)
        visit(rule, lambda x: maybe_compile_error_message(out, rule, x))

    return out


def _assign_ids(rules):
    next_id = 1

    def assign_id(node):
        nonlocal next_id
        node.program_id = next_id
        next_id += 1
        if isinstance(node, Class):
            node.extra_id = next_id
            next_id += 1

    visit(rules, assign_id)


def _update_local_references(rules):
    counter = ex.SymbolCounter()

    def previsit(node):
        counter.previsit(node)
        if node.is_reference and counter.is_bound(node.name):
            node.is_local = True

    visit(rules, previsit, counter.postvisit)


def _update_rule_references(rules):
    rule_names = set()
    for rule in rules:
        if isinstance(rule, (Class, Rule)):
            rule_names.add(rule.name)

    def check_refs(node):
        if isinstance(node, Ref) and node.name in rule_names and not node.is_local:
            node._resolved = ex.implementation_name(node.name)

    visit(rules, check_refs)


_program_setup = r'''
from collections import namedtuple as _nt
from re import compile as _compile_re, IGNORECASE as _IGNORECASE

class Node:
    _fields = ()

    def __init__(self):
        self._metadata = _Metadata()

    def __eq__(self, other):
        if not isinstance(other, self.__class__):
            return False
        for field in self._fields:
            if getattr(self, field) != getattr(other, field):
                return False
        return True

    def _asdict(self):
        return {k: getattr(self, k) for k in self._fields}

    def _replace(self, **kw):
        for field in self._fields:
            if field not in kw:
                kw[field] = getattr(self, field)
        result = self.__class__(**kw)
        result._metadata._fields.update(self._metadata._fields)
        return result


class _Metadata:
    def __init__(self, **fields):
        object.__setattr__(self, '_fields', fields)

    def __getattr__(self, name):
        return self._fields.get(name)

    def __setattr__(self, name, value):
        self._fields[name] = value

    def copy(self):
        return _Metadata(**self._fields)


class Rule:
    def __init__(self, name, parse, definition):
        self.name = name
        self.parse = parse
        self.definition = definition

    def __repr__(self):
        return (f'Rule(name={self.name!r}, parse={self.parse.__name__},'
            f' definition={self.definition!r})')
'''


_main_template = r'''
class SourcerError(Exception):
    """Common superclass for ParseError and PartialParseError."""


class ParseError(SourcerError):
    def __init__(self, message, index, line, column):
        super().__init__(message)
        self.position = _Position(index, line, column)


class PartialParseError(SourcerError):
    def __init__(self, partial_result, last_position, excerpt):
        super().__init__('Incomplete parse. Unexpected input on line'
            f' {last_position.line}, column {last_position.column}:\n{excerpt}')
        self.partial_result = partial_result
        self.last_position = last_position


class Infix(Node):
    _fields = ('left', 'operator', 'right')

    def __init__(self, left, operator, right):
        Node.__init__(self)
        self.left = left
        self.operator = operator
        self.right = right

    def __repr__(self):
        return f'Infix({self.left!r}, {self.operator!r}, {self.right!r})'


class Postfix(Node):
    _fields = ('left', 'operator')

    def __init__(self, left, operator):
        Node.__init__(self)
        self.left = left
        self.operator = operator

    def __repr__(self):
        return f'Postfix({self.left!r}, {self.operator!r})'


class Prefix(Node):
    _fields = ('operator', 'right')

    def __init__(self, operator, right):
        Node.__init__(self)
        self.operator = operator
        self.right = right

    def __repr__(self):
        return f'Prefix({self.operator!r}, {self.right!r})'


def parse(text, pos=0, fullparse=True):
    return _run(text, pos, $start, fullparse)


_PositionInfo = _nt('_PositionInfo', 'start, end')

_Position = _nt('_Position', 'index, line, column')


class _ParseFunction(_nt('_ParseFunction', 'func, args, kwargs')):
    def __call__(self, _text, _pos):
        return self.func(_text, _pos, *self.args, **dict(self.kwargs))


class _StringLiteral(str):
    def __call__(self, _text, _pos):
        return self._parse_function(_text, _pos)


def _wrap_string_literal(string_value, parse_function):
    result = _StringLiteral(string_value)
    result._parse_function = parse_function
    return result


def _run(text, pos, start, fullparse):
    memo = {}
    result = None

    key = ($CALL, start, pos)
    gtor = start(text, pos)
    stack = [(key, gtor)]

    while stack:
        key, gtor = stack[-1]
        result = gtor.send(result)

        if result[0] != $CALL:
            stack.pop()
            memo[key] = result
        elif result in memo:
            result = memo[result]
        else:
            gtor = result[1](text, result[2])
            stack.append((result, gtor))
            result = None

    if result[0]:
        return _finalize_parse_info(text, result[1], result[2], fullparse)
    else:
        pos = result[2]
        message = result[1](text, pos)
        raise ParseError(message, pos)


def visit(node):
    visited = set()
    stack = [node]
    while stack:
        node = stack.pop()

        if isinstance(node, (list, tuple)):
            stack.extend(node)

        elif isinstance(node, dict):
            stack.extend(node.values())

        elif isinstance(node, Node):
            node_id = id(node)
            if node_id in visited:
                continue
            visited.add(node_id)

            yield node

            if hasattr(node, '_fields'):
                stack.extend(getattr(node, x) for x in node._fields)


def transform(node, *callbacks):
    if not callbacks:
        return node

    if len(callbacks) == 1:
        callback = callbacks[0]
    else:
        def callback(node):
            for f in callbacks:
                node = f(node)
            return node

    return _transform(node, callback)


def _transform(node, callback):
    if isinstance(node, list):
        return [_transform(x, callback) for x in node]

    if not isinstance(node, Node):
        return node

    updates = {}
    for field in node._fields:
        was = getattr(node, field)
        now = _transform(was, callback)
        if was is not now:
            updates[field] = now

    if updates:
        node = node._replace(**updates)

    return callback(node)


def _finalize_parse_info(text, nodes, pos, fullparse):
    line_numbers, column_numbers = _map_index_to_line_and_column(text)

    for node in visit(nodes):
        pos_info = node._metadata.position_info
        if pos_info:
            start, end = pos_info
            end -= 1
            node._metadata.position_info = _PositionInfo(
                start=_Position(start, line_numbers[start], column_numbers[start]),
                end=_Position(end, line_numbers[end], column_numbers[end]),
            )

    if fullparse and pos < len(text):
        line, col = line_numbers[pos], column_numbers[pos]
        position = _Position(pos, line, col)
        excerpt = _extract_excerpt(text, pos, col)
        raise PartialParseError(nodes, position, excerpt)

    return nodes


def _extract_excerpt(text, pos, col):
    if isinstance(text, bytes):
        return repr(text[max(0, pos - 1) : pos + 2])

    start = pos - (col - 1)
    match = _compile_re('\n').search(text, pos + 1)
    end = len(text) if match is None else match.start()

    if end - start < 96:
        return text[start : end] + _caret_at(col - 1)

    if col < 60:
        # Chop the line off at the end.
        return text[start : start + 90] + ' ...' + _caret_at(col - 1)

    elif end - pos < 40:
        # Chop the line off at the start.
        return '... ' + text[end - 90 : end] + _caret_at(pos - (end - 90) + 4)

    else:
        # Chop the line off at both ends.
        return '... ' + text[pos - 42 : pos + 42] + ' ...' + _caret_at(42 + 4)


def _caret_at(index):
    return '\n' + (' ' * index) + '^'


def _get_line_and_column(text, pos):
    line_numbers, column_numbers = _map_index_to_line_and_column(text)
    return line_numbers[pos], column_numbers[pos]


def _map_index_to_line_and_column(text):
    line_numbers = []
    column_numbers = []

    current_line = 1
    current_column = 0

    for c in text:
        if c == '\n':
            current_line += 1
            current_column = 0
        else:
            current_column += 1
        line_numbers.append(current_line)
        column_numbers.append(current_column)

    return line_numbers, column_numbers
'''
