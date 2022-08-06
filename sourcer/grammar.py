import ast
import importlib
import re
import sys
import types

from . import expressions as ex
from . import parser
from . import translator


def Grammar(description, include_source=False):
    # Parse the grammar description.
    head, body = _parse_grammar(description)

    # Create the docstring for the module.
    docstring = '# Grammar definition:\n' + description

    # Convert the parse tree into a list of parsing expressions.
    nodes = parser.transform(body, _create_parsing_expression)

    # Grab the name of the grammar.
    name = head.name if head else 'grammar'

    # If we have a super-grammar, then prepend those nodes.
    if head is not None and head.extends is not None:
        super_body = _get_super_tree(head.extends)
        super_body.extend(body)
        body = super_body

    # Generate and compile the souce code.
    builder = translator.generate_source_code(docstring, nodes)
    module = builder.compile(
        module_name=name,
        docstring=docstring,
        source_var='_source_code' if include_source else None,
    )

    if head.name:
        _install_module(name, module)

    return module


def _get_super_tree(name):
    module = importlib.import_module(name)
    head, body = _parse_grammar(module.__doc__)

    for node in parser.visit(body):
        if isinstance(node, parser.Node):
            node._metatadata.module_name = name

    if head is None or head.extends is None:
        return body

    super_body = _get_super_tree(head.extends)
    super_body.extend(body)
    return super_body


def _parse_grammar(description):
    tree = parser.parse(description)
    assert isinstance(tree, parser.GrammarDef)
    head, body = tree.head, tree.body

    # If the body is just an expression, create an implicit 'start' rule.
    if not isinstance(body, list):
        body = [
            parser.RuleDef(
                is_override=False,
                is_ignored=False,
                name='start',
                params=None,
                expr=body,
            ),
        ]

    return head, body


def _create_parsing_expression(node):
    if isinstance(node, parser.StringLiteral):
        ignore_case = node.value.endswith(('i', 'I'))
        value = ast.literal_eval(node.value[:-1] if ignore_case else node.value)
        if ignore_case:
            return ex.Regex(re.escape(value), ignore_case=True)
        else:
            return ex.Str(value)

    if isinstance(node, parser.RegexLiteral):
        is_binary = node.value.startswith('b')
        ignore_case = node.value.endswith(('i', 'I'))
        value = node.value

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

    if isinstance(node, parser.ByteLiteral):
        return ex.Byte(node.value)

    if isinstance(node, parser.PythonExpression):
        return ex.PythonExpression(node.value)

    if isinstance(node, parser.PythonSection):
        return ex.PythonSection(node.value)

    if isinstance(node, parser.Ref):
        return ex.Ref(node.value)

    if isinstance(node, parser.LetExpression):
        return ex.Let(node.name, node.expr, node.body)

    if isinstance(node, parser.ListLiteral):
        return ex.Seq(*node.elements)

    if isinstance(node, parser.ArgList):
        return node

    if isinstance(node, parser.Postfix) and isinstance(node.operator, parser.ArgList):
        left, args = node.left, node.operator.args
        if isinstance(left, ex.Ref) and hasattr(ex, left.name):
            return getattr(ex, left.name)(
                *[unwrap(x) for x in args if not isinstance(x, ex.KeywordArg)],
                **{x.name: unwrap(x.expr) for x in args if isinstance(x, ex.KeywordArg)},
            )
        else:
            return ex.Call(left, args)

    if isinstance(node, parser.Postfix):
        classes = {
            '?': ex.Opt,
            '*': ex.List,
            '+': ex.Some,
        }
        if isinstance(node.operator, str) and node.operator in classes:
            return classes[node.operator](node.left)

        if isinstance(node.operator, parser.Repeat):
            start = uncook(node.operator.start)
            stop = uncook(node.operator.stop)
            return ex.List(node.left, min_len=start, max_len=stop)

    if isinstance(node, parser.Repeat):
        return node

    if isinstance(node, parser.Infix) and node.operator == '|':
        left, right = node.left, node.right
        left = list(left.exprs) if isinstance(left, ex.Choice) else [left]
        right = list(right.exprs) if isinstance(right, ex.Choice) else [right]
        return ex.Choice(*left, *right)

    if isinstance(node, parser.Infix):
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

    if isinstance(node, parser.KeywordArg):
        return ex.KeywordArg(node.name, node.expr)

    if isinstance(node, parser.RuleDef):
        return ex.Rule(node.name, node.params, node.expr, is_ignored=node.is_ignored)

    if isinstance(node, parser.ClassDef):
        return ex.Class(node.name, node.params, node.members)

    if isinstance(node, parser.ClassMember):
        return ex.Rule(node.name, None, node.expr, is_omitted=node.is_omitted)

    if isinstance(node, parser.IgnoreStmt):
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


def _install_module(name, module):
    if '.' not in name:
        sys.modules[name] = module
        return

    parent_name, child_name = name.rsplit('.', 1)
    try:
        parent_module = importlib.import_module(parent_name)
    except ModuleNotFoundError:
        parent_module = types.ModuleType(parent_name)
        _install_module(parent_name, parent_module)
        setattr(parent_module, child_name, module)
