# JSON

Maybe you have to parse something that is a little bit like JSON, but different
enough that you can't use a real JSON parser.

Here's a simple example that you can start with and work from, and build it up
into what you need.

```python
from sourcer import Grammar

g = Grammar(r'''
    `from ast import literal_eval`

    start = Value

    Value = Object
        | Array
        | String
        | Number
        | Keyword

    Object = "{" >> (Member // ",") << "}" |> `dict`

    Member = [String << ":", Value]

    Array = "[" >> (Value // ",") << "]"

    String = /"(?:[^\\"]|\\.)*"/ |> `literal_eval`

    Number = /-?(?:0|[1-9]\d*)(?:\.\d+)?(?:[eE][+-]?\d+)?/ |> `float`

    Keyword = "true" >> `True`
        | "false" >> `False`
        | "null" >> `None`

    ignore /\s+/
''')
```

The grammar is compiled to a Python module, which is assigned to the variable ``g``.
The module defines a ``parse`` function, which you can use to parse strings:

```python
>>> g.parse('123')
123.0

>>> g.parse('{}')
{}

>>> g.parse('[123, -456, [], [789, "ten-eleven"]]')
[123.0, -456.0, [], [789.0, 'ten-eleven']]

>>> g.parse('{"foo": true, "bar": false}')
{'foo': True, 'bar': False}

>>> g.parse('{"name": "Foobar", "counts": [10, 25], "active": true, "parent": null}')
{'name': 'Foobar', 'counts': [10.0, 25.0], 'active': True, 'parent': None}
```

Notice that this parser returns native Python dicts, lists, strings, booleans, etc:

```python
result = g.parse('{"foo": "bar", "baz": true}')
assert result == {'foo': 'bar', 'baz': True}

result = g.parse('[12, -34, {"56": 78, "foo": null}]')
assert result == [12, -34, {'56': 78, 'foo': None}]
```
