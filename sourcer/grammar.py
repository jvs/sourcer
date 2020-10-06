import types

from .parsing_expressions import *
from . import parsing_expressions
from . import meta


def Grammar(description, name='grammar', include_source=False):
    # Parse the grammar description.
    raw = meta.parse(description)

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
        return StringLiteral(node.value)

    if isinstance(node, meta.RegexLiteral):
        return RegexLiteral(node.value)

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
        left = node.left
        if isinstance(left, Ref) and hasattr(parsing_expressions, left.name):
            return getattr(parsing_expressions, left.name)(*node.operator.args)
        else:
            return Call(left, node.operator.args)

    if isinstance(node, meta.Postfix):
        classes = {
            '?': Opt,
            '*': List,
            '+': Some,
        }
        if isinstance(node.operator, str) and node.operator in classes:
            return classes[node.operator](node.left)

    if isinstance(node, meta.Infix) and node.operator == '|':
        left, right = node.left, node.right
        left = list(left.exprs) if isinstance(left, Choice) else [left]
        right = list(right.exprs) if isinstance(right, Choice) else [right]
        return Choice(*left, *right)

    if isinstance(node, meta.Infix):
        classes = {
            '|>': lambda a, b: Apply(a, b, apply_left=False),
            '<|': lambda a, b: Apply(a, b, apply_left=True),
            '/': lambda a, b: Alt(a, b, allow_trailer=True),
            '//': lambda a, b: Alt(a, b, allow_trailer=False),
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

    # Otherwise, fail if we don't know what to do with this node.
    raise Exception(f'Unexpected expression: {node!r}')
