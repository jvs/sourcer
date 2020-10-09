# Alternation

Alternation is when you have a list of elements separated by a separator.
Sourcer discards the separators and produces a list of the elements.

Sourcer gives you a few ways to use alternation:

* `foo // bar` -- does not consume a trailing separator
* `foo /? bar` -- consumes an optional trailing separator
* ``Alt(foo, bar, allow_trailer=`False`, allow_empty=`True`)`` -- verbose form


## Alternation without a trailing separator

```python
from sourcer import Grammar

g = Grammar('start = "fiz" // ", "')

assert g.parse('fiz, fiz, fiz') == ['fiz', 'fiz', 'fiz']

try:
    # This will raise a "PartialParseError", meaning it couldn't parse the whole input.
    g.parse('fiz, fiz,')
    assert False
except g.PartialParseError as exc:
    assert exc.partial_result == ['fiz', 'fiz']
    assert exc.last_position.column == 9
```


## Alternation with an optional trailing separator

```python
from sourcer import Grammar

g = Grammar('start = "buz" /? "!"')

assert g.parse('buz!buz') == ['buz', 'buz']
assert g.parse('buz!buz!') == ['buz', 'buz']
```


## Requiring a non-empty result

The `//` and `/?` operators both accept an empty list of items. If you want to
require the list to be non-empty, then you can use the verbose form:

```python
from sourcer import Grammar

g = Grammar('start = Alt("bif", "$", allow_empty=`False`)')

assert g.parse('bif$bif') == ['bif', 'bif']

try:
    g.parse('')
    assert False
except g.ParseError:
    pass
```


## Requiring a trailing separator

If you want to require a trailing separator, then you can use a repetition
expression, like `(foo << bar)*`. This particular expression means, "Parse
a list of pairs of `foo` and `bar`, discarding each `bar`."

```python
from sourcer import Grammar

g = Grammar('start = ("zim" << ".")*')

assert g.parse('zim.zim.') == ['zim', 'zim']

try:
    g.parse('zim.zim.zim')
    assert False
except g.PartialParseError as exc:
    assert exc.partial_result == ['zim', 'zim']
```


## Keeping the separators instead of discarding them

If you don't want to discard the separators, then you'd also use repetition.
For example, the expression `[foo, [bar, foo]*] | []` gets you most of the way
there, but you may also want to flatten the result into one list.

```python
from sourcer import Grammar

g = Grammar(r'''
    start = ["zam", [";", "zam"]*]
        |> `lambda a: [a[0]] + [c for b in a[1] for c in b]`
        | []
''')

assert g.parse('zam;zam;zam') == ['zam', ';', 'zam', ';', 'zam']
```
