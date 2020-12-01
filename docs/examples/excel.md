# Excel Formulas

This example shows how to parse Excel formula with Sourcer.


```python
from sourcer import Grammar

g = Grammar(r'''
    `from ast import literal_eval`

    start = Formula
    Formula = "="? >> Expr

    ignored Space = /[ \t\n\r]+/

    Offset = /\d+|\[\-?\d+\]/ |> `literal_eval`

    class R1C1Ref {
        row = "R" >> Offset
        col = "C" >> Offset
    }

    class A1Ref {
        col_modifier = "$"?
        col = /I[A-V]|[A-H][A-Z]|[A-Z]/
        row_modifier = "$"?
        row = /\d+/
    }

    class DateTime {
        string = /\d{4}-\d\d-\d\d \d\d:\d\d:\d\d/
    }

    Word = /[a-zA-Z_\@][a-zA-Z0-9_\.\@]*/

    LongNumber = /[0-9]\.[0-9]+(e|E)(\+|\-)[0-9]+/ |> `literal_eval`
    ShortNumber = /[0-9]+(\.[0-9]*)?|\.[0-9]+/ |> `literal_eval`

    String = /"([^"]|"")*"/ |> `lambda x: x[1:-1].replace('""', '"')`
    Sheet = /'([^']|'')*'/ |> `lambda x: x[1:-1].repalce("''", "'")`

    Error = /\#[a-zA-Z0-9_\/]+(\!|\?)?/ |> `lambda x: {'error': x}`

    Array = "{" >> (ExprList /? ";") << "}"

    class FunctionCall {
        name = Word
        arguments = "(" >> ExprList << ")"
    }

    class CellRef {
        book = Opt("[" >> (Word | String) << "]")
        sheet = Opt((R1C1Ref | A1Ref | Word | Sheet) << "!")
        cell = R1C1Ref | A1Ref
    }

    Atom = "(" >> Expr << ")"
        | Array
        | FunctionCall
        | CellRef
        | Word
        | ShortNumber
        | LongNumber
        | String
        | DateTime
        | Error

    Operators(allow_union) => OperatorPrecedence(
        Atom,
        LeftAssoc(":"),
        LeftAssoc(""),
        LeftAssoc("," where `lambda _: allow_union`),
        Prefix("-" | "+"),
        Postfix("%"),
        RightAssoc("^"),
        LeftAssoc("*" | "/"),
        LeftAssoc("+" | "-"),
        LeftAssoc("&"),
        LeftAssoc("=" | "!=" | "<>" | "<=" | ">=" | "<" | ">"),
    )

    Expr = Operators(allow_union=True)
    ExprList = Operators(allow_union=False)? /? ","
''')
```

The grammar is compiled to a Python module, which is assigned to the variable ``g``.
The module defines a ``parse`` function, which you can use to parse strings:

```python
>>> g.parse('={1, 2; 3, 4}')
[[1, 2], [3, 4]]

>>> g.parse('1 + R2C3')
Infix(1, '+', CellRef(book=None, sheet=None, cell=R1C1Ref(row=2, col=3)))
```

Sourcer takes the classes that you define in your grammar
(like `CellRef` and `R1C1Ref` in this case),
and turns them into Python classes.
The classes are defined in your grammar module.
(In this case, the grammar module assigned to the variable `g`.)

Here's an example of how to use these classes in a test:

```python
result = g.parse('=SUM(B5:B15)')
assert result == g.FunctionCall(
    name='SUM',
    arguments=[
        g.Infix(
            left=g.CellRef(
                book=None,
                sheet=None,
                cell=g.A1Ref(
                    col_modifier=None, col='B',
                    row_modifier=None, row='5',
                ),
            ),
            operator=':',
            right=g.CellRef(
                book=None,
                sheet=None,
                cell=g.A1Ref(
                    col_modifier=None, col='B',
                    row_modifier=None, row='15',
                ),
            ),
        ),
    ],
)
```
