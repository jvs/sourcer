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

The grammar is compiled to a Python module, which is assigned to the variable
``g``. The module defines a ``parse`` function, which you can use to parse
strings:

```python
>>> commands = g.parse('Print [10, 20); Delete (33, 44];')
>>> len(commands)
2

>>> commands[0]
Command(action='Print', range=Range(start='[', left=10, right=20, end=')'))

>>> commands[1]
Command(action='Delete', range=Range(start='(', left=33, right=44, end=']'))
```

The Command objects have position information:

```python
>>> info = commands[0]._position_info
>>> info.start
_Position(index=0, line=1, column=1)

>>> info.end
_Position(index=13, line=1, column=14)
```


The ``Command``, ``Range``, and ``_Position`` classes are defined in the grammar
module, ``g``.

```python
# The `g` module defines the `Command` and `Range` classes. For example:
assert g.parse('Copy [1, 2]; Delete [3, 4]') == [
    g.Command(action='Copy', range=g.Range('[', 1, 2, ']')),
    g.Command(action='Delete', range=g.Range('[', 3, 4, ']')),
]

# The `g` module also defines the `_Position` class.
command = g.parse('Print (5, 6)')
assert command[0]._position_info.start == g._Position(index=0, line=1, column=1)
```

This means you can generate a Python source file for your grammar, and use it
in projects, without having to depend on the Sourcer library in those other
projects.

Sourcer turns your grammar into a standalone Python module with zero dependencies
outside of the standard library.
