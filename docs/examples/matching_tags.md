
# Matching Tags

Maybe you have to parse something where you have matching start and end tags.
Here's a simple example that you can work from. It shows how Sourcer can handle
some data-dependent grammars.

<!-- SETUP -->
```python
from sourcer import Grammar

g = Grammar(r'''
    # A document is a list of one or more items:
    Document = Item+

    # An item is either an element, an empty element, or some text:
    Item = Element | EmptyElement | Text

    # An element is a pair of matching tags, and zero or more items:
    class Element {
        open: "<" >> Tag << ">"
        items: Item*
        close: "</" >> Tag << ">" where `lambda x: x == open`
    }

    # An empty element is just a tag.
    class EmptyElement {
        tag: "<" >> Tag << "/>"
    }

    # Text goes until it sees a "<" character:
    class Text {
        content: /[^<]+/
    }

    # A tag is a Word surrounded by optional whitespace.
    Tag = /\s*/ >> Word << /\s*/

    # A word doesn't have special characters, and doesn't start with a digit:
    Word = /[_a-zA-Z][_a-zA-Z0-9]*/
''')
```

The grammar is compiled to a Python module, which is assigned to the variable ``g``.

The module defines a ``Document`` object, which you can use to parse strings:

<!-- TEST -->
```python
result = g.Document.parse('To: <party><b>Second</b> Floor Only</party><br/>')

assert result == [
    g.Text('To: '),
    g.Element(
        open='party',
        items=[
            g.Element('b', [g.Text('Second')], 'b'),
            g.Text(' Floor Only'),
        ],
        close='party',
    ),
    g.EmptyElement('br'),
]
```


Similarly, we can use any of our other rules directly, too. For example, maybe
we just want to parse a single item:

<!-- TEST -->
```python
assert g.Item.parse('< span />') == g.EmptyElement('span')
```
