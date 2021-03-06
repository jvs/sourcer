# Separated Lists

Sometimes you may want to parse a list of elements that are separated by a
separator, like "," or something.
Sourcer has special operators for this, that discard the separators and produce
the list of elements.

* `foo // bar` -- a list of `foo` separated by `bar`, with no trailing `bar`.
* `foo /? bar` -- same as `foo // bar`, only allows an optional trailing `bar`.
* ``Sep(foo, bar, discard_separators=True, allow_trailer=False, allow_empty=True)``
  -- the verbose form, which supports additional options.


## Separated list without a trailing separator

Use the `//` operator to parse a separated list with no trailing separator. This
means that the parser fails when the input includes a trailing separator.

<!-- fresh example -->
```python
from sourcer import Grammar

g = Grammar('''
    "fiz" // ","
''')
```

We can use this grammar to parse a list, as long as it doesn't end with a `,`
character:

```python
>>> g.parse('fiz,fiz,fiz')
['fiz', 'fiz', 'fiz']

>>> g.parse('')
[]

>>> g.parse('fiz')
['fiz']
```

In this example, our `parse` function fails if it see a trailing comma:

```python
try:
    # This will raise a "PartialParseError", meaning it couldn't parse the whole input.
    g.parse('fiz,fiz,')
    assert False
except g.PartialParseError as exc:
    assert exc.partial_result == ['fiz', 'fiz']
    assert exc.last_position.column == 8
```


## Separated list with optional trailing separator

Use the `/?` operator to parse a separated list with an optional trailing
separator. This means that the input can include a final separator on the end of
the list, but the final separator is not required.

<!-- fresh example -->
```python
from sourcer import Grammar

g = Grammar('''
    "buz" /? "!"
''')
```

The grammar allows lists to include trailing `!` character, but it does not
require a trailing `!` character.

```python
>>> g.parse('buz!buz')
['buz', 'buz']

>>> g.parse('buz!buz!')
['buz', 'buz']

>>> g.parse('')
[]
```


## Requiring a non-empty result

The `//` and `/?` operators both accept an empty list of items. If you want to
require the list to be non-empty, then you can use the verbose form:

<!-- fresh example -->
```python
from sourcer import Grammar

g = Grammar('''
    Sep("bif", "$", allow_empty=False)
''')
```

In this example, we can parse a non-empty list, of course:

```python
>>> g.parse('bif$bif')
['bif', 'bif']
```

But we'll get a `ParseError` if we try to parse an empty list:

```python
try:
    g.parse('')
    assert False
except g.ParseError:
    pass
```


## Keeping the separators instead of discarding them

By default, the `//` and `/?` operators discard the separators.
If you want to keep the separators, you can use the `Sep` constructor:

<!-- fresh example -->
```python
from sourcer import Grammar

g = Grammar('''
    Sep("zim" | "zam", ";" | "-", discard_separators=False)
''')
```

When we parse a list, the result will include the `;` and `-` characters:

```python
>>> g.parse('zim-zam;zim')
['zim', '-', 'zam', ';', 'zim']
```

Of course, a separator may be any parsing expression. It doesn't have to be
a string. Here's a more complex example:

<!-- fresh example -->
```python
from sourcer import Grammar

g = Grammar(r'''
    start = Sep(Statement, Separator, discard_separators=False, allow_trailer=True)

    Statement = [Command, Location] |> `tuple`

    Command = "go" | "stay" | "sleep"
    Location = "here" | "there" | "anywhere"

    class Separator {
        marker: "--"
        urgency: "now" | "soon" | "later"
        terminator: "." | "!"
    }

    ignore /\s+/
''')
```

This time, the results will include more interesting separators:

```python
commands = g.parse('go there -- now! stay here -- later.')

assert commands == [
    ('go', 'there'),
    g.Separator(marker='--', urgency='now', terminator='!'),
    ('stay', 'here'),
    g.Separator(marker='--', urgency='later', terminator='.'),
]
```


## Requiring a trailing separator

If you want to require a trailing separator, then you can use a repetition
expression, like `(foo << bar)*`. This particular expression means, "Parse
a list of pairs of `foo` and `bar`, discarding each `bar`."

<!-- fresh example -->
```python
from sourcer import Grammar

g = Grammar('''
    ("zim" << ".")*
''')
```

```python
>>> g.parse('zim.zim.')
['zim', 'zim']

>>> g.parse('zim.')
['zim']

>>> g.parse('')
[]
```

The parser fails if we omit the trailing `.` character:

```python
exc = None

try:
    g.parse('zim.zim.zim')
except g.PartialParseError as e:
    exc = e

assert exc.partial_result == ['zim', 'zim']
```
