from sourcer import Grammar

# This is work in progress.
# See: https://help.salesforce.com/articleView?id=customize_functions.htm&type=5

g = Grammar(r'''
    ```
    import ast
    ```

    start = Expression

    Expression = OperatorPrecedence(
        Atom | "(" >> Expression << ")",
        Postfix(ArgumentList | FieldAccess),
        Prefix("-" | "+" | "!"),
        RightAssoc("^"),
        LeftAssoc("*" | "/"),
        LeftAssoc("+" | "-" | "&"),
        NonAssoc("<=" | "<" | ">=" | ">"),
        NonAssoc("!=" | "<>" | "==" | "="),
        LeftAssoc("&&"),
        LeftAssoc("||"),
    )

    class ArgumentList {
        arguments: "(" >> (Expression /? ",") << ")"
    }

    class FieldAccess {
        field: "." >> Word
    }

    Atom = Global | Identifier | Rational | Integer | String

    class Global {
        name: "$" >> Word
    }

    class Identifier {
        name: Word
    }

    # ASK: What is the real syntax for these things?
    Word = /[_a-zA-Z][_a-zA-Z0-9]*/
    Rational = /(\d+\.\d*)|(\d*\.\d+)/ |> `float`
    Integer = /\d+/ |> `int`
    StringLiteral = /("([^"\\]|\\.)*")/ | /('([^'\\]|\\.)*')/

    # For now, just use ast module to evaluate string literals.
    class String {
        value: StringLiteral |> `ast.literal_eval`
    }

    ignore Space = /\s+/

''', include_source=True)


aliases = {
    '=': '==',
    '<>': '!=',
}


constants = {
    'NULL': None,
    'TRUE': True,
    'FALSE': False,
}


# Incomplete collection of evaluators.
evaluators = {
    '*': lambda x, y: x * y if x is not None and y is not None else None,
    '/': lambda x, y: x / y if x is not None and y is not None else None,
    '+': lambda x, y: x + y if x is not None and y is not None else None,
    '-': lambda x, y: x - y if x is not None and y is not None else None,
    '==': lambda x, y: x == y,
    '!=': lambda x, y: x != y,
    '&&': lambda x, y: x and y,
    '||': lambda x, y: x or y,
    '>': lambda x, y: x > y if x is not None and y is not None else False,
    '<': lambda x, y: x < y if x is not None and y is not None else False,
    '>=': lambda x, y: x >= y if x is not None and y is not None else False,
    '<=': lambda x, y: x <= y if x is not None and y is not None else False,
    'AND': lambda *a: all(a),
    'CONTAINS': lambda x, y: str(y) in str(x) if x is not None else True,
    'IF': lambda x, y, z: y if x else z,
    'ISBLANK': lambda x: x is None,
    'LOG': lambda x: log10(x) if x is not None else None,
    'MAX': lambda *a: max(*a),
    'MIN': lambda *a: min(*a),
    'MOD': lambda x, y: (x % y) if x is not None and y is not None else None,
    'NOT': lambda x: not(x),
    'OR': lambda *a: any(a),
    'SQRT': lambda x: sqrt(x) if x is not None else None,
    'TEXT': lambda x: str(x),
}


def evaluate(node, bindings):
    # Lookup identifiers.
    if isinstance(node, g.Identifier):
        if node.name in bindings:
            return bindings[node.name]

        name = node.name.upper()
        return bindings.get(name, name)

    # Lookup fields.
    if isinstance(node, g.Postfix) and isinstance(node.operator, g.FieldAccess):
        obj, field = node.left, node.operator.field
        if hasattr(obj, field):
            return getattr(obj, field)
        elif isinstance(obj, dict):
            return obj.get(field)
        else:
            return node

    # Evaluate function calls and operators.
    if isinstance(node, g.Infix):
        x, func, y = node.left, node.operator, node.right
        args = (x, y)
    elif isinstance(node, g.Postfix) and isinstance(node.operator, g.ArgumentList):
        func, args = node.left, node.operator.arguments
    else:
        return node

    # Check if we're using an alias.
    func = aliases.get(func, func)

    if func in evaluators:
        return evaluators[func](*args)
    else:
        return node


def run(formula, bindings=None):
    updated_bindings = dict(constants)
    updated_bindings.update(bindings or {})
    tree = g.parse(formula)
    return g.transform(tree, lambda node: evaluate(node, updated_bindings))


def test_some_simple_formulas():
    result = run('1 + 2 * 3')
    assert result == 7

    result = run('foo == bar && fiz == buz', bindings={
        'foo': 1, 'bar': 1, 'fiz': 2, 'buz': 2,
    })
    assert result == True

    result = run('foo == bar && fiz == buz', bindings={
        'foo': 1, 'bar': 1, 'fiz': 2, 'buz': 3,
    })
    assert result == False

    result = run('1 <= 2 && (false || true)')
    assert result == True # Explicitly compare to True.

    result = run('1 > 2 || (true && false)')
    assert result == False # Explicitly compare to False.

    result = run('foo != bar', bindings={'foo': 10, 'bar': 10})
    assert not result

    result = run('foo != bar', bindings={'foo': 1, 'bar': 2})
    assert result

    result = run('foo.bar', bindings={'foo': {'bar': 10}})
    assert result == 10

    result = run('foo.bar.baz', bindings={'foo': {'bar': {'baz': 100}}})
    assert result == 100

    result = run('MIN(20, 10, 30)')
    assert result == 10

    result = run('MIN(20, 10, 30) + MAX(11, 12, 13)')
    assert result == 23
