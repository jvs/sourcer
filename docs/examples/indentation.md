# Indentation

If you ever need to parse something with significant indentation, you can start
with this example and build it up.

```python
from sourcer import Grammar

g = Grammar(r'''
    ignore /[ \t]+/

    Indent = /\n[ \t]*/

    MatchIndent(i) =>
        Indent where `lambda x: x == i`

    IncreaseIndent(i) =>
        Indent where `lambda x: len(x) > len(i)`

    Body(current_indent) =>
        let i = IncreaseIndent(current_indent) in
        Statement(i) // MatchIndent(i)

    Statement(current_indent) =>
        If(current_indent) | Print

    class If(current_indent) {
        test: "if" >> Name
        body: Body(current_indent)
    }

    class Print {
        name: "print" >> Name
    }

    Name = /[a-zA-Z]+/
    Newline = /[\r\n]+/

    Start = Opt(Newline) >> (Statement('') /? Newline)
''')
```

The grammar is compiled to a Python module, which is assigned to the variable ``g``.

The module defines a ``parse`` function, which you can use to parse strings:

```python
result = g.parse('''

print ok
if foo
    if bar
        print baz
        print fiz
    print buz
print zim

''')

assert result == [
    g.Print('ok'),
    g.If('foo', [
        g.If('bar', [
            g.Print('baz'),
            g.Print('fiz'),
        ]),
        g.Print('buz'),
    ]),
    g.Print('zim'),
]
```
