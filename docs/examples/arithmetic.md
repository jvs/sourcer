# Arithmetic Expressions

Here's a simple grammar for arithmetic expressions.

<!-- SETUP -->
```python
from sourcer import Grammar

g = Grammar(r'''
    start = Expr

    # Define operatator precedence, from highest to lowest.
    Expr = OperatorPrecedence(
        Int | Parens,
        Prefix('+' | '-'),
        RightAssoc('^'),
        Postfix('%'),
        LeftAssoc('*' | '/'),
        LeftAssoc('+' | '-'),
    )

    # Discard parentheses.
    Parens = '(' >> Expr << ')'

    # Turn integers into Python int objects.
    Int = /\d+/ |> `int`

    # Ignore whitespace.
    ignore /\s+/
''')
```

<!-- HIDDEN TEST
assert g.parse('1 + 2 + 3') == g.Infix(g.Infix(1, '+', 2), '+', 3)
assert g.parse('4 + -5 / 6') == g.Infix(4, '+', g.Infix(g.Prefix('-', 5), '/', 6))
assert g.parse('7 * (8 + 9)') == g.Infix(7, '*', g.Infix(8, '+', 9))
assert g.parse('10 * 20%') == g.Infix(10, '*', g.Postfix(20, '%'))
-->

The grammar is compiled to a Python module, which is assigned to the variable ``g``.

The module defines a ``parse`` function, which you can use to parse strings.

<!-- CONSOLE -->
```python
>>> g.parse('1 + 2 + 3')
Infix(Infix(1, '+', 2), '+', 3)

>>> g.parse('4 + -5 / 6')
Infix(4, '+', Infix(Prefix('-', 5), '/', 6))
```

The grammar module defines classes named ``Infix``, ``Prefix``, and ``Postfix``
to represent the parse tree.
(Note that these classes are defined in the compiled grammar module, and not in
the Sourcer module.)

You can use this classes in your tests, to make assertions like these:

<!-- TEST -->
```python
assert g.parse('7 * (8 + 9)') == g.Infix(7, '*', g.Infix(8, '+', 9))
assert g.parse('10 * 20%') == g.Infix(10, '*', g.Postfix(20, '%'))
```
