
# Matching Tags

Maybe you have to parse something where you have matching start and end tags.
Here's a simple example that you can work from. It shows how Sourcer can handle
some data-dependent grammars.

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

```python
>>> g.Document.parse('fiz')
[Text(content='fiz')]

>>> g.Document.parse('<buz/>')
[EmptyElement(tag='buz')]

>>> g.Document.parse('<foo>bar</foo>')
[Element(open='foo', items=[Text(content='bar')], close='foo')]

>>> g.Document.parse('zim <i>zam</i>')
[Text(content='zim '), Element(open='i', items=[Text(content='zam')], close='i')]
```

You can use any of the rules defined in the grammar this way. For example:

```python
>>> g.Item.parse('<msg>hello <select/></msg>')
Element(open='msg', items=[Text(content='hello '), EmptyElement(tag='select')], close='msg')

>>> g.Item.parse('< input />')
EmptyElement(tag='input')

>>> g.Element.parse('<h1>OK</h1>')
Element(open='h1', items=[Text(content='OK')], close='h1')

>>> g.EmptyElement.parse('<br/>')
EmptyElement(tag='br')

>>> g.Text.parse('bim bam boz')
Text(content='bim bam boz')

>>> g.Tag.parse(' open ')
'open'

>>> g.Word.parse('here')
'here'
```

We can uses the grammar's classes directly in our tests, to validate the parser:

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
