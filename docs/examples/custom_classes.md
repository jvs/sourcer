# Custom Classes

This is a short example to show how you can define classes within your grammars.

Classes let you define the kinds of objects that you want to get back when you
parse something.

```python
from sourcer import Grammar

g = Grammar(r'''
    # A list of commands separated by semicolons.
    start = Command /? ";"

    # A pair of action and range.
    class Command {
        action: "Copy" | "Delete" | "Print"
        range: Range
    }

    # A range (which can be open or closed on either end).
    class Range {
        start: "(" | "["
        left: Int << ","
        right: Int
        end: "]" | ")"
    }

    # Integers.
    Int = /\d+/ |> `int`

    ignore /\s+/
''')

```

The grammar is compiled to a Python module, which is assigned to the variable ``g``.

The module defines a ``parse`` function, which you can use to parse strings:

```python
result = g.parse('Print [10, 20); Delete (33, 44];')
assert result == [
    g.Command(action='Print', range=g.Range('[', 10, 20, ')')),
    g.Command(action='Delete', range=g.Range('(', 33, 44, ']')),
]

cmd = result[1]
assert cmd.action == 'Delete'

# The Command objects have position information:
info = cmd._position_info
assert info.start == g._Position(index=16, line=1, column=17)
assert info.end == g._Position(index=30, line=1, column=31)
```

The point of classes is to give you a way to name the things that you want.
Instead of traversing some opaque tree structure to get what you want, Sourcer
gives you normal Python objects, that you define.
