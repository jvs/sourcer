import ast
import re
import types

from .parsing_expressions import *
from . import parsing_expressions
from . import meta


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
    source_code = parsing_expressions.generate_source_code(docstring, nodes)
    code_object = compile(source_code, f'<{name}>', 'exec', optimize=2)
    module = types.ModuleType(name, doc=docstring)
    exec(code_object, module.__dict__)

    # Optionally include the source code.
    if include_source and not hasattr(module, '_source_code'):
        module._source_code = source_code

    return module


def _create_parsing_expression(node):
    if isinstance(node, meta.StringLiteral):
        ignore_case = node.value.endswith(('i', 'I'))
        value = ast.literal_eval(node.value[:-1] if ignore_case else node.value)
        if ignore_case:
            return RegexLiteral(re.escape(value), ignore_case=True)
        else:
            return StringLiteral(value)

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

        return RegexLiteral(value, ignore_case=ignore_case)

    if isinstance(node, meta.PythonExpression):
        return PythonExpression(node.value)

    if isinstance(node, meta.PythonSection):
        return PythonSection(node.value)

    if isinstance(node, meta.Ref):
        return Ref(node.value)

    if isinstance(node, meta.LetExpression):
        return LetExpression(node.name, node.expr, node.body)

    if isinstance(node, meta.ListLiteral):
        return Seq(*node.elements)

    if isinstance(node, meta.ArgList):
        return node

    if isinstance(node, meta.Postfix) and isinstance(node.operator, meta.ArgList):
        left, args = node.left, node.operator.args
        if isinstance(left, Ref) and hasattr(parsing_expressions, left.name):
            return getattr(parsing_expressions, left.name)(
                *[unwrap(x) for x in args if not isinstance(x, KeywordArg)],
                **{x.name: unwrap(x.expr) for x in args if isinstance(x, KeywordArg)},
            )
        else:
            return Call(left, args)

    if isinstance(node, meta.Postfix):
        classes = {
            '?': Opt,
            '*': List,
            '+': Some,
        }
        if isinstance(node.operator, str) and node.operator in classes:
            return classes[node.operator](node.left)

        if isinstance(node.operator, meta.Repeat):
            start = uncook(node.operator.start)
            stop = uncook(node.operator.stop)
            return List(node.left, min_len=start, max_len=stop)

    if isinstance(node, meta.Repeat):
        return node

    if isinstance(node, meta.Infix) and node.operator == '|':
        left, right = node.left, node.right
        left = list(left.exprs) if isinstance(left, Choice) else [left]
        right = list(right.exprs) if isinstance(right, Choice) else [right]
        return Choice(*left, *right)

    if isinstance(node, meta.Infix):
        classes = {
            '|>': lambda a, b: Apply(a, b, apply_left=False),
            '<|': lambda a, b: Apply(a, b, apply_left=True),
            '/?': lambda a, b: Sep(a, b, allow_trailer=True),
            '//': lambda a, b: Sep(a, b, allow_trailer=False),
            '<<': Left,
            '>>': Right,
            'where': Where,
        }
        return classes[node.operator](node.left, node.right)

    if isinstance(node, meta.KeywordArg):
        return KeywordArg(node.name, node.expr)

    if isinstance(node, meta.RuleDef):
        return Rule(node.name, node.params, node.expr, is_ignored=node.is_ignored)

    if isinstance(node, meta.ClassDef):
        return Class(node.name, node.params, node.fields)

    if isinstance(node, meta.IgnoreStmt):
        return Rule(None, None, node.expr, is_ignored=True)

    # Otherwise, fail if we don't know what to do with this node.
    raise Exception(f'Unexpected expression: {node!r}')


def unwrap(x):
    return eval(x.source_code) if isinstance(x, PythonExpression) else x


def uncook(x):
    if x is None:
        return None
    if isinstance(x, PythonExpression) and x.source_code == 'None':
        return None
    if isinstance(x, PythonExpression):
        return x.source_code
    if isinstance(x, Ref):
        return x.name

    raise Exception(f'Expected name or Python expression. Received: {x}')
