import ast
import re
from string import Template

from outsourcer import CodeBuilder, Code, Val

from . import expressions as ex
from . import parser
from .expressions import TEXT, POS, Ref, visit


def generate_source_code(docstring, parsed):
    # Convert the parse tree into a list of parsing expressions.
    nodes = parser.transform(parsed.body, _create_parsing_expression)

    out = CodeBuilder()
    out.add_docstring(docstring)

    flags = _Flags(uses_context=parsed.name is not None)

    if parsed.extends is None:
        out += Code(_program_setup)
    else:
        out += Code(Template(_subgrammar_setup).substitute(
            super_module=parsed.extends.name,
        ))

    if flags.uses_context and parsed.extends is None:
        out += Code(_context_section)

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
            f'The {start_rule!r} rule must not have the "ignore" modifier.'
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

    super_has_ignore = False
    ancestor = parsed.extends
    while ancestor is not None and not super_has_ignore:
        for stmt in ancestor.body:
            is_ignored_rule = isinstance(stmt, parser.RuleDef) and stmt.is_ignored
            is_ignored_expr = isinstance(stmt, parser.IgnoreStmt)
            if is_ignored_rule or is_ignored_expr:
                super_has_ignore = True
                break
        ancestor = ancestor.extends

    if ignored:
        # Create a rule called "_ignored" that skips all the ignored rules.
        refs = [Ref(x.name) for x in ignored]

        if super_has_ignore:
            refs.append(Ref('_super_ctx._ignored'))

        rules.append(ex.Rule('_ignored', None, ex.Skip(*refs), 'ignored'))

    if ignored or super_has_ignore:
        # If we have a start rule, then update its expression to skip ahead past
        # any leading ignored stuff.
        if isinstance(start_rule, ex.Class):
            first_rule = start_rule.fields[0] if start_rule.fields else None
        else:
            first_rule = start_rule

        if first_rule:
            assert isinstance(first_rule, ex.Rule)
            impl_name = ex.implementation_name('_ignored')
            first_rule.expr = ex.Right(Ref(impl_name), first_rule.expr)

        # Update the "skip_ignored" flag of each literal.
        def _set_skip_ignored(expr):
            if hasattr(expr, 'skip_ignored'):
                expr.skip_ignored = True

        for rule in rules:
            if not rule.is_ignored:
                visit(rules, _set_skip_ignored)

    _assign_ids(rules)
    _update_local_references(rules)
    _update_rule_references(rules, parsed.extends)

    if start_rule is not None:
        start_name = ex.implementation_name(start_rule.name)
    else:
        start_name = None
        ancestor = parsed.extends
        while start_name is None and ancestor is not None:
            for stmt in ancestor.body:
                if hasattr(stmt, 'name') and stmt.name.lower() == 'start':
                    start_name = f'_ctx.{ex.implementation_name(stmt.name)}'
                    break
            ancestor = ancestor.extends

    if start_name is None:
        start_name = ex.implementation_name(rules[0].name)

    if parsed.extends is None:
        out += Code(Template(_main_template).substitute(
            CALL=ex.CALL,
            ctx='_ctx, ' if flags.uses_context else '',
            start=start_name,
        ))
    else:
        out += Code(Template(_subgrammar_body).substitute(
            start=start_name,
        ))

    error_delegates = {}
    def set_error_delegate(expr):
        if not isinstance(expr, ex.Choice):
            return
        real, fail = [], []
        for option in expr.exprs:
            if isinstance(option, ex.Fail):
                fail.append(option)
            else:
                real.append(option)
        if not real or not fail:
            return
        delegate = ex.Choice(*real)
        error_delegates[fail[-1].program_id] = ex.Choice(*real)

    for rule in rules:
        visit(rule, set_error_delegate)

    visited = set()
    def maybe_compile_error_message(out, rule, expr):
        if (
            not hasattr(expr, 'complain')
            or expr.program_id is None
            or expr.program_id in visited
        ):
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
        rule.compile(out, flags)
        visit(rule, lambda x: maybe_compile_error_message(out, rule, x))

    if flags.uses_context:
        out += Code('_ctx = _Context()')

        if parsed.extends is not None:
            out += Code('_ctx._super_ctx = _super_ctx')

        if super_has_ignore and not ignored:
            impl_name = ex.implementation_name('_ignored')
            out += Code(f'_ctx.{impl_name} = _super_ctx.{impl_name}')

        if ignored:
            impl_name = ex.implementation_name('_ignored')
            out += Code(f'_ctx.{impl_name} = {impl_name}')

        visited_names = set()
        more_imports = []

        for rule in rules:
            if hasattr(rule, 'name'):
                impl_name = ex.implementation_name(rule.name)
                out += Code(f'_ctx.{impl_name} = {impl_name}')
                visited_names.add(rule.name)

        ancestor = parsed.extends
        while ancestor is not None:
            for stmt in ancestor.body:
                if hasattr(stmt, 'name') and stmt.name not in visited_names:
                    impl_name = ex.implementation_name(stmt.name)
                    out += Code(f'_ctx.{impl_name} = _super_ctx.{impl_name}')
                    visited_names.add(stmt.name)
                    more_imports.append(stmt.name)
            ancestor = ancestor.extends

        if more_imports:
            lines = ',\n    '.join(sorted(more_imports))
            out.append_global(Code(
                f'from {parsed.extends.name} import (\n    {lines}\n)'
            ))

    return out


class _Flags:
    def __init__(self, uses_context):
        self.uses_context = uses_context


def _assign_ids(rules):
    next_id = 1

    def assign_id(node):
        nonlocal next_id
        if getattr(node, 'program_id', None) is not None:
            return
        node.program_id = next_id
        next_id += 1
        if isinstance(node, ex.Class):
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


def _update_rule_references(rules, extends):
    rule_names = set()
    for rule in rules:
        if isinstance(rule, (ex.Class, ex.Rule)):
            rule_names.add(rule.name)

    if extends is not None:
        for stmt in extends.body:
            if hasattr(stmt, 'name'):
                rule_names.add(stmt.name)

    def check_refs(node):
        if isinstance(node, Ref) and node.name in rule_names and not node.is_local:
            node._resolved = ex.implementation_name(node.name)

    visit(rules, check_refs)


def _create_parsing_expression(tree):
    if isinstance(tree, parser.StringLiteral):
        ignore_case = tree.value.endswith(('i', 'I'))
        value = ast.literal_eval(tree.value[:-1] if ignore_case else tree.value)
        if ignore_case:
            return ex.Regex(re.escape(value), ignore_case=True)
        else:
            return ex.Str(value)

    if isinstance(tree, parser.RegexLiteral):
        is_binary = tree.value.startswith('b')
        ignore_case = tree.value.endswith(('i', 'I'))
        value = tree.value

        # Remove leading 'b'.
        if is_binary:
            value = value[1:]

        # Remove trailing 'i'.
        if ignore_case:
            value = value[:-1]

        # Remove /slash/ delimiters.
        value = value[1:-1]

        # Enocde binary string.
        if is_binary:
            value = value.encode('ascii')

        return ex.Regex(value, ignore_case=ignore_case)

    if isinstance(tree, parser.ByteLiteral):
        return ex.Byte(tree.value)

    if isinstance(tree, parser.PythonExpression):
        return ex.PythonExpression(tree.value)

    if isinstance(tree, parser.PythonSection):
        return ex.PythonSection(tree.value)

    if isinstance(tree, parser.Ref):
        return ex.Ref(tree.value)

    if isinstance(tree, parser.LetExpression):
        return ex.Let(tree.name, tree.expr, tree.body)

    if isinstance(tree, parser.ListLiteral):
        return ex.Seq(*tree.elements)

    if isinstance(tree, parser.ArgList):
        return tree

    if isinstance(tree, parser.Postfix) and isinstance(tree.operator, parser.ArgList):
        left, args = tree.left, tree.operator.args
        if isinstance(left, ex.Ref) and hasattr(ex, left.name):
            def unwrap(x):
                return eval(x.source_code) if isinstance(x, ex.PythonExpression) else x
            return getattr(ex, left.name)(
                *[unwrap(x) for x in args if not isinstance(x, ex.KeywordArg)],
                **{x.name: unwrap(x.expr) for x in args if isinstance(x, ex.KeywordArg)},
            )
        else:
            return ex.Call(left, args)

    if isinstance(tree, (parser.OperatorTable, parser.OperatorRow)):
        return tree

    if isinstance(tree, parser.Postfix) and isinstance(tree.operator, parser.OperatorTable):
        rows = tree.operator.rows
        if rows:
            return ex.OperatorTable.create(operand=tree.left, rows=rows)
        else:
            return tree.left

    if isinstance(tree, parser.Postfix):
        left, op = tree.left, tree.operator
        classes = {
            '?': ex.Opt,
            '*': ex.List,
            '+': ex.Some,
        }
        if isinstance(op, str) and op in classes:
            return classes[op](left)

        if isinstance(op, parser.FieldAccess):
            if isinstance(left, ex.Ref) and left.name == 'super':
                impl_name = ex.implementation_name(op.field)
                result = ex.Ref(f'super.{op.field}')
                result._resolved = f'_super_ctx.{impl_name}'
                return result

        if isinstance(op, parser.Repeat):
            def uncook(x):
                if x is None:
                    return None
                if isinstance(x, ex.PythonExpression) and x.source_code == 'None':
                    return None
                if isinstance(x, ex.PythonExpression):
                    return x.source_code
                if isinstance(x, ex.Ref):
                    return x.name
                else:
                    raise Exception(f'Expected name or Python expression. Received: {x}')

            start = uncook(op.start)
            stop = uncook(op.stop)
            return ex.List(left, min_len=start, max_len=stop)

    if isinstance(tree, (parser.Repeat, parser.FieldAccess)):
        return tree

    if isinstance(tree, parser.Infix) and tree.operator == '|':
        left, right = tree.left, tree.right
        left = list(left.exprs) if isinstance(left, ex.Choice) else [left]
        right = list(right.exprs) if isinstance(right, ex.Choice) else [right]
        return ex.Choice(*left, *right)

    if isinstance(tree, parser.Infix):
        classes = {
            '|>': lambda a, b: ex.Apply(a, b, apply_left=False),
            '<|': lambda a, b: ex.Apply(a, b, apply_left=True),
            '/?': lambda a, b: ex.Sep(a, b, allow_trailer=True),
            '//': lambda a, b: ex.Sep(a, b, allow_trailer=False),
            '<<': ex.Left,
            '>>': ex.Right,
            'where': ex.Where,
        }
        return classes[tree.operator](tree.left, tree.right)

    if isinstance(tree, parser.KeywordArg):
        return ex.KeywordArg(tree.name, tree.expr)

    if isinstance(tree, parser.RuleDef):
        return ex.Rule(tree.name, tree.params, tree.expr, is_ignored=tree.is_ignored)

    if isinstance(tree, parser.ClassDef):
        return ex.Class(tree.name, tree.params, tree.members)

    if isinstance(tree, parser.ClassMember):
        return ex.Rule(tree.name, None, tree.expr, is_omitted=tree.is_omitted)

    if isinstance(tree, parser.IgnoreStmt):
        return ex.Rule(None, None, tree.expr, is_ignored=True)

    # Otherwise, fail if we don't know what to do with this tree.
    raise Exception(f'Unexpected expression: {tree!r}')


_program_setup = r'''
from collections import namedtuple as _nt
from re import compile as _compile_re, IGNORECASE as _IGNORECASE

class Node:
    _fields = ()

    def __init__(self):
        self._metadata = _Metadata()
        self._hash = None

    def __eq__(self, other):
        if self is other:
            return True
        if not isinstance(other, self.__class__):
            return False
        for field in self._fields:
            left = getattr(self, field)
            right = getattr(other, field)
            if left is not right and left != right:
                return False
        return True

    def __hash__(self):
        if self._hash is not None:
            return self._hash
        self._hash = 0
        result = 0
        for field in self._fields:
            result ^= _hash(getattr(self, field))
        self._hash = result
        return result

    def _asdict(self):
        return {k: getattr(self, k) for k in self._fields}

    def _replace(self, **kw):
        for field in self._fields:
            if field not in kw:
                kw[field] = getattr(self, field)
        result = self.__class__(**kw)
        result._metadata.update(self._metadata)
        return result


def _hash(value):
    try:
        return hash(value)
    except TypeError:
        if isinstance(value, (tuple, list)):
            result = 0
            for item in value:
                result ^= _hash(item)
            return result
        elif isinstance(value, dict):
            result = 0
            for pair in value.items():
                result ^= _hash(pair)
            return result
        else:
            raise


class _Metadata:
    def __init__(self, **fields):
        object.__setattr__(self, '_fields', fields)

    def __getattr__(self, name):
        return self._fields.get(name)

    def __setattr__(self, name, value):
        self._fields[name] = value

    def __len__(self):
        return len(self._fields)

    def copy(self):
        return _Metadata(**self._fields)

    def update(self, other):
        self._fields.update(other._fields)


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
class InputError(Exception):
    """Common superclass for ParseError and PartialParseError."""


class ParseError(InputError):
    def __init__(self, message, index, line, column):
        super().__init__(message)
        self.position = _Position(index, line, column)


class PartialParseError(InputError):
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
    return _run(${ctx}text, pos, $start, fullparse)


_PositionInfo = _nt('_PositionInfo', 'start, end')

_Position = _nt('_Position', 'index, line, column')


class _ParseFunction(_nt('_ParseFunction', 'func, args, kwargs')):
    def __call__(self, ${ctx}_text, _pos):
        return self.func(${ctx}_text, _pos, *self.args, **dict(self.kwargs))


class _StringLiteral(str):
    def __call__(self, ${ctx}_text, _pos):
        return self._parse_function(${ctx}_text, _pos)


def _wrap_string_literal(string_value, parse_function):
    result = _StringLiteral(string_value)
    result._parse_function = parse_function
    return result


class _ByteLiteral(int):
    def __call__(self, ${ctx}_text, _pos):
        return self._parse_function(${ctx}_text, _pos)


def _wrap_byte_literal(byte_value, parse_function):
    result = _ByteLiteral(byte_value)
    result._parse_function = parse_function
    return result


def _run(${ctx}text, pos, start, fullparse):
    memo = {}
    result = None

    key = ($CALL, start, pos)
    gtor = start(${ctx}text, pos)
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
            gtor = result[1](${ctx}text, result[2])
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
            stack.extend(reversed(node))

        elif isinstance(node, dict):
            stack.extend(reversed(node.values()))

        elif isinstance(node, Node):
            node_id = id(node)
            if node_id in visited:
                continue
            visited.add(node_id)

            yield node

            if hasattr(node, '_fields'):
                stack.extend(getattr(node, x) for x in reversed(node._fields))


_Traversing = _nt('_Traversing', 'parent, field, child, is_finished')


def traverse(node):
    visited = set()
    stack = [_Traversing(parent=None, field=None, child=node, is_finished=False)]
    while stack:
        traversing = stack.pop()

        if traversing.is_finished:
            yield traversing
            continue

        child = traversing.child
        child_id = id(child)

        if child_id in visited:
            continue

        visited.add(child_id)
        stack.append(traversing._replace(is_finished=True))
        yield traversing

        def extend(items):
            stack.extend(reversed(list(items)))

        if isinstance(child, (list, tuple)):
            extend(
                _Traversing(parent=child, field=i, child=x, is_finished=False)
                for i, x in enumerate(child)
            )

        elif isinstance(child, dict):
            extend(
                _Traversing(parent=child, field=k, child=v, is_finished=False)
                for k, v in child.items()
            )

        elif isinstance(child, Node) and hasattr(child, '_fields'):
            extend(
                _Traversing(
                    parent=child,
                    field=x,
                    child=getattr(child, x),
                    is_finished=False,
                )
                for x in child._fields
            )


def transform(node, *callbacks):
    if not callbacks:
        return node

    def callback(node):
        for f in callbacks:
            prev = node
            node = f(prev)

            if node is not prev:
                if (
                    isinstance(prev, Node)
                    and isinstance(node, Node)
                    and not node._metadata
                ):
                    node._metadata.update(prev._metadata)

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
        if now is not was:
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


_context_section = '''
class _Context:
    pass
'''


_subgrammar_setup = r'''
from $super_module import (
    Infix,
    InputError,
    Node,
    ParseError,
    PartialParseError,
    Postfix,
    Prefix,
    Rule,
    _ByteLiteral,
    _Context,
    _IGNORECASE,
    _Metadata,
    _ParseFunction,
    _Position,
    _PositionInfo,
    _StringLiteral,
    _Traversing,
    _caret_at,
    _compile_re,
    _extract_excerpt,
    _finalize_parse_info,
    _get_line_and_column,
    _map_index_to_line_and_column,
    _nt,
    _run,
    _transform,
    _wrap_byte_literal,
    _wrap_string_literal,
    transform,
    traverse,
    visit,
    _ctx as _super_ctx,
)
'''

_subgrammar_body = '''
def parse(text, pos=0, fullparse=True):
    return _run(_ctx, text, pos, $start, fullparse)
'''
