import ast
import re

from . import expressions as ex
from . import meta
from . import translator


def Grammar(description, name='grammar', include_source=False):
    # Parse the grammar description.
    raw = meta.parse(description)

    # If the grammar is just an expression, create an implicit 'start' rule.
    if not isinstance(raw, list):
        raw = [meta.RuleDef(is_ignored=False, name='start', params=None, expr=raw)]

    # Create the docstring for the module.
    docstring = '# Grammar definition:\n' + description

    # Convert the parse tree into a list of parsing expressions.
    nodes = meta.transform(raw, _create_parsing_expression)

    # Generate and compile the souce code.
    builder = translator.generate_source_code(docstring, nodes)
    return builder.compile(
        module_name=name,
        docstring=docstring,
        source_var='_source_code' if include_source else None,
    )


def _create_parsing_expression(node):
    if isinstance(node, meta.StringLiteral):
        ignore_case = node.value.endswith(('i', 'I'))
        value = ast.literal_eval(node.value[:-1] if ignore_case else node.value)
        if ignore_case:
            return ex.Regex(re.escape(value), ignore_case=True)
        else:
            return ex.Str(value)

    if isinstance(node, meta.RegexLiteral):
        is_binary = node.value.startswith('b')
        ignore_case = node.value.endswith(('i', 'I'))
        value = node.value

        # Remove leading 'b'.
        if is_binary:
            value = value[1:]

        # Remove trailing 'i'.
        if ignore_case:
            value = value[:-1]

        # Remove backslashes.
        value = value[1:-1]

        # Enocde binary string.
        if is_binary:
            value = value.encode('ascii')

        return ex.Regex(value, ignore_case=ignore_case)

    if isinstance(node, meta.PythonExpression):
        return ex.PythonExpression(node.value)

    if isinstance(node, meta.PythonSection):
        return ex.PythonSection(node.value)

    if isinstance(node, meta.Ref):
        return ex.Ref(node.value)

    if isinstance(node, meta.LetExpression):
        return ex.Let(node.name, node.expr, node.body)

    if isinstance(node, meta.ListLiteral):
        return ex.Seq(*node.elements)

    if isinstance(node, meta.ArgList):
        return node

    if isinstance(node, meta.Postfix) and isinstance(node.operator, meta.ArgList):
        left, args = node.left, node.operator.args
        if isinstance(left, ex.Ref) and hasattr(ex, left.name):
            return getattr(ex, left.name)(
                *[unwrap(x) for x in args if not isinstance(x, ex.KeywordArg)],
                **{x.name: unwrap(x.expr) for x in args if isinstance(x, ex.KeywordArg)},
            )
        else:
            return ex.Call(left, args)

    if isinstance(node, meta.Postfix):
        classes = {
            '?': ex.Opt,
            '*': ex.List,
            '+': ex.Some,
        }
        if isinstance(node.operator, str) and node.operator in classes:
            return classes[node.operator](node.left)

        if isinstance(node.operator, meta.Repeat):
            start = uncook(node.operator.start)
            stop = uncook(node.operator.stop)
            return ex.List(node.left, min_len=start, max_len=stop)

    if isinstance(node, meta.Repeat):
        return node

    if isinstance(node, meta.Infix) and node.operator == '|':
        left, right = node.left, node.right
        left = list(left.exprs) if isinstance(left, ex.Choice) else [left]
        right = list(right.exprs) if isinstance(right, ex.Choice) else [right]
        return ex.Choice(*left, *right)

    if isinstance(node, meta.Infix):
        classes = {
            '|>': lambda a, b: ex.Apply(a, b, apply_left=False),
            '<|': lambda a, b: ex.Apply(a, b, apply_left=True),
            '/?': lambda a, b: ex.Sep(a, b, allow_trailer=True),
            '//': lambda a, b: ex.Sep(a, b, allow_trailer=False),
            '<<': ex.Left,
            '>>': ex.Right,
            'where': ex.Where,
        }
        return classes[node.operator](node.left, node.right)

    if isinstance(node, meta.KeywordArg):
        return ex.KeywordArg(node.name, node.expr)

    if isinstance(node, meta.RuleDef):
        return ex.Rule(node.name, node.params, node.expr, is_ignored=node.is_ignored)

    if isinstance(node, meta.ClassDef):
        return ex.Class(node.name, node.params, node.fields)

    if isinstance(node, meta.IgnoreStmt):
        return ex.Rule(None, None, node.expr, is_ignored=True)

    # Otherwise, fail if we don't know what to do with this node.
    raise Exception(f'Unexpected expression: {node!r}')


def unwrap(x):
    return eval(x.source_code) if isinstance(x, ex.PythonExpression) else x


def uncook(x):
    if x is None:
        return None
    if isinstance(x, ex.PythonExpression) and x.source_code == 'None':
        return None
    if isinstance(x, ex.PythonExpression):
        return x.source_code
    if isinstance(x, ex.Ref):
        return x.name

    raise Exception(f'Expected name or Python expression. Received: {x}')
