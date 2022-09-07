import importlib
import sys
import types

from . import parser
from . import translator


def Grammar(description, include_source=False):
    # Parse the grammar description.
    parsed = _parse_grammar(description)

    # Create the docstring for the module.
    docstring = '# Grammar definition:\n' + description

    # Grab the name of the grammar.
    name = parsed.name or 'grammar'

    # Generate and compile the souce code.
    builder = translator.generate_source_code(docstring, parsed)
    module = builder.compile(
        module_name=name,
        docstring=docstring,
        source_var='_source_code' if include_source else None,
    )

    if parsed.name:
        _install_module(name, module)

    return module


class _ParsedGrammar:
    def __init__(self, name, extends, body):
        self.name = name
        self.extends = extends
        self.body = body


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

    if head is None or head.extends is None:
        extends = None
    else:
        module = importlib.import_module(head.extends)
        extends = _parse_grammar(module.__doc__)

    return _ParsedGrammar(
        name=None if head is None else head.name,
        extends=extends,
        body=body,
    )


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
