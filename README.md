# Sourcer

A parsing library for Python (version 3.6 and later).

```python
from sourcer import Grammar

g = Grammar(r'''
    start = "Hello" >> @/[a-zA-Z]+/

    ignore Space = @/[ \t]+/
    ignore Punctuation = "," | "." | "!" | "?"
''')

# Try it out:
result = g.parse('Hello, World!')
assert result == 'World'

result = g.parse('Hello Chief?!?!!')
assert result == 'Chief'
```

Notes:

* `>>` means "discard the the left hand side"
* `@/.../` means "regular expression"


## Installation

```console
$ python3 -m pip install sourcer
```


## Why Use Sourcer?

Sometimes you have to parse things, and sometimes a regex won't cut it.

Things you might have to parse someday:

- log files
- business rules
- market data feeds
- equations
- queries
- user input
- domain specific languages
- obscure data formats
- legacy source code

So that's what this library is for. It's for when you have to take some text
and turn it into a tree of Python objects.


#### Aren't there a ton of parsing libraries for Python already?

&lt;rant&gt;Yes. But there's always so much ceremony involved. The main point of
Sourcer is that you can just define the thing that you really want, and then get
on with your life. (Hopefully the examples will drive this home.)&lt;/rant&gt;


## Features

- Supports Python version 3.6 and later.
- Create parsers at runtime, or generate Python source code as part of your build.
- Implements [Parsing Expression Grammars](http://en.wikipedia.org/wiki/Parsing_expression_grammar)
  (where "|" represents ordered choice).
- Built-in support for operator precedence parsing.
- Supports inline Python, for defining predicates and transformations directly
  within grammars.
- Supports class definitions for defining the structure of your parse trees.
- Each rule in a grammar becomes a top-level function in the generated Python
  module, so you can use a grammar as a parsing library, rather than just a
  monolithic "parse" function.
- Supports data dependent rules, for things like:
    - significant indentation
    - matching start and end tags


## Examples


### Arithmetic Expressions

Here's a barebones grammar for arithmetic expressions. You can build it up with
your own operators, say if you're parsing equations of some sort.

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
    Int = @/\d+/ |> `int`

    # Ignore whitespace.
    ignore Space = @/\s+/
''')

# Note: The Grammar is compiled to a Python modulea and assigned to "g".

# Left associativity:
result = g.parse('1 + 2 + 3')
assert result == g.Infix(g.Infix(1, '+', 2), '+', 3)

# Operator precedence:
result = g.parse('4 + -5 / 6')
assert result == g.Infix(4, '+', g.Infix(g.Prefix('-', 5), '/', 6))

# Parentheses:
result = g.parse('7 * (8 + 9)')
assert result == g.Infix(7, '*', g.Infix(8, '+', 9))
```


### Something Like JSON

Maybe you have to parse something that is a little bit like JSON, but different
enough that you can't use a real JSON parser.

Here's a simple example that you can start with and work from, and build it up
into what you need.

```python
from sourcer import Grammar

g = Grammar(r'''
    # Import Python modules by quoting your import statement in backticks.
    # (You can also use triple backticks to quote multiple lines at once.)
    `from ast import literal_eval`

    # This grammar parses one value.
    start = Value

    # A value is one of these things.
    Value = Object | Array | String | Number | Keyword

    # An object is zero or more members separated by commas, enclosed in
    # curly braces. Convert each into a Python dict.
    Object = "{" >> (Member // ",") << "}" |> `dict`

    # A member is a pair of string literal and value, separated by a colon.
    Member = [String << ":", Value]

    # An array is zero or more values separated by commas, enclosed in
    # square braces.
    Array = "[" >> (Value // ",") << "]"

    # Interpret each string as a Python literal string.
    String = @/"(?:[^\\"]|\\.)*"/ |> `literal_eval`

    # Interpret each number as a Python float literal.
    Number = @/-?(?:0|[1-9]\d*)(?:\.\d+)?(?:[eE][+-]?\d+)?/ |> `float`

    # Convert boolean literals to Python booleans, and "null" to None.
    Keyword = "true" >> `True` | "false" >> `False` | "null" >> `None`

    ignored Space = @/\s+/
''')

# Notice that we get back Python dicts, lists, strings, booleans, etc.
result = g.parse('{"foo": "bar", "baz": true}')
assert result == {'foo': 'bar', 'baz': True}

result = g.parse('[12, -34, {"56": 78, "foo": null}]')
assert result == [12, -34, {'56': 78, 'foo': None}]
```

This example how Sourcer lets you define what you want, and then get on with
your life. This example parses something remarkably close to JSON with just
10 lines of actual code (ignoring all my chatty comments).


### Using Classes

This is a short example to show how you can define classes within your grammars.

Classes let you define the kinds of objects that you want to get back when you
parse something.

```python
from sourcer import Grammar

g = Grammar(r'''
    # A list of commands separated by semicolons.
    start = Command / ";"

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
    Int = @/\d+/ |> `int`

    ignore Space = @/\s+/
''')

result = g.parse('Print [10, 20); Delete (33, 44];')
assert result == [
    g.Command(action='Print', range=g.Range('[', 10, 20, ')')),
    g.Command(action='Delete', range=g.Range('(', 33, 44, ']')),
]

cmd = result[1]
assert cmd.action == 'Delete'

# Objects created from these classes have position information:
info = cmd._position_info
assert info.start == g._Position(index=16, line=1, column=17)
assert info.end == g._Position(index=30, line=1, column=31)
```

The point of classes is to give you a way to name the things that you want.
Instead of traversing some opaque tree structure to get what you want, Sourcer
gives you normal Python objects, that you define.



### Something Like XML

Maybe you have to parse something where you have matching start and end tags.
Here's a simple example that you can work from.

It shows how Sourcer can handle some data-dependent grammars.

```python
from sourcer import Grammar

g = Grammar(r'''
    # A document is a list of one or more items:
    Document = Item+

    # An item is either an element or some text:
    Item = Element | Text

    # Text goes until it sees a "<" character:
    class Text {
        content: @/[^<]+/
    }

    # An element is a pair of matching tags, and zero or more items:
    class Element {
        open: "<" >> Word << ">"
        items: Item*
        close: "</" >> Word << ">" where `lambda x: x == open`
    }

    # A word doesn't have special characters, and doesn't start with a digit:
    Word = @/[_a-zA-Z][_a-zA-Z0-9]*/
''')

# We can use the "Document" rule directly:
result = g.Document.parse('To: <party><b>Second</b> Floor Only</party>')

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
]

# Similarly, we can use any of our other rules directly, too. For example, maybe
# we just want to parse a single word:
result = g.Word.parse('booyah')
assert result == 'booyah' # (But yes, this doesn't really accomplish anything...)
```


### Significant Indentation

If you ever need to parse something with significant indentation, you can start
with this example and build it up.

```python
from sourcer import Grammar

g = Grammar(r'''
    ignore Space = @/[ \t]+/

    Indent = @/\n[ \t]*/

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

    Name = @/[a-zA-Z]+/
    Newline = @/[\r\n]+/

    Start = Opt(Newline) >> (Statement('') / Newline)
''')

from textwrap import dedent

result = g.parse('print ok\nprint bye')
assert result == [g.Print('ok'), g.Print('bye')]

result = g.parse('if foo\n  print bar')
assert result == [g.If('foo', [g.Print('bar')])]

result = g.parse(dedent('''
    print ok
    if foo
        if bar
            print baz
            print fiz
        print buz
    print zim
'''))
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


### More Examples

[Excel formula](https://github.com/jvs/sourcer/tree/master/examples)
and some corresponding
[test cases](https://github.com/jvs/sourcer/blob/master/tests/test_excel.py)


## Background
[Parsing expression grammar](http://en.wikipedia.org/wiki/Parsing_expression_grammar>)

The main thing to know is that the `|` operator represents an ordered choice.


## Parsing Expressions

This is work in progress. The goal is to provide examples of each of the
different parsing expressions.

For now, here's a list of the supported expressions:

- Alternation:

    - `foo / bar` -- parses a list of foo separated by bar, consuming
      an optional trailing separator
    - `foo // bar` -- parses a list of foo separated by bar, and does
      not consume a trailing separator
    - In both cases, returns the list of foo values and discards the bar
      values

- Application:

    - `foo |> bar` -- parses foo then parses bar, then returns `bar(foo)`
    - `foo <| bar` -- parses foo then parses bar, then returns `foo(bar)`

- Binding:

    - `let foo = bar in baz` -- parses bar, binding the result to foo, then
      parses baz

- Class:

    - `class Foo { bar: Bar; baz: Baz }` -- defines a sequence of named elements

- Expectation:

    - `Expect(foo)` -- parses foo without consuming any input
    - `ExpectNot(foo)` -- fails if it can parse foo

- Failure:

    - `Fail(message)` -- fails with the provided error message

- Invocation:

    - `foo(bar)` -- parses the rule foo using the parsing expression bar

- OperatorPrecedence:

    - `OperatorPrecedence(...)` -- defines an operator precedence table

- Option:

    - `foo?` -- parse foo, if that fails then return `None`
    - `Opt(foo)` -- verbose form of `foo?`

- Ordered Choice:

    - `foo | bar` -- parses foo, and if that fails, then tries bar

- Python Expression:

    - `` `foo` `` -- returns the Python value `foo`

- Predicate:

    - `foo where bar` -- parses foo, then bar, returning foo only if
      `bar(foo)` returns `True` (or some other truthy value)

- Projection:

    - `foo >> bar` -- parses foo, then parses bar, returning only bar
    - `foo << bar` -- parses foo, then parses bar, returning only foo

- Regular Expression:

    - `@/foo/` -- matches the regular expression foo
    - `@/foo/i` -- matches the regular expression foo, ignoring case
    - `@/(?i)foo/` -- matches the regular expression foo, also ignoring case

- Repetition:

    - `foo*` -- parses foo zero or more times, returning the results in a list
    - `foo+` -- parses foo one or more times
    - `List(foo)` -- verbose form of `foo*`
    - `Some(foo)` -- verbose form of `foo+`

- Sequence:

    - `[foo, bar, baz]` -- parses foo, then bar, then baz, returning the
      results in a list

- String Matching:

    - `'foo'` -- matches the string 'foo'
    - `'foo'i` -- matches the string 'foo', ignoring case


### Alternation

```python
from sourcer import Grammar

g = Grammar(r'''
    # Alternation -- with optional trailing separator:
    Statements = Statement / ";"

    # Alternation -- without trailing separator:
    Arguments = Argument // ","

    Statement = Word+
    Argument = Word
    Word = @/\w+/

    ignore Space = @/\s+/
''')

# Use optional trailing separator:
result = g.Statements.parse('print this; do that;')
assert result == [['print', 'this'], ['do', 'that']]

# Omit optional trailing separator:
result = g.Statements.parse('go here; then stop')
assert result == [['go', 'here'], ['then', 'stop']]

# Try using optional separator where it's not allowed:
try:
    result = g.Arguments.parse('these, those, theirs,')
    assert False
except g.PartialParseError as exc:
    assert exc.partial_result == ['these', 'those', 'theirs']
    assert exc.last_position.index == 20
```


## Grammar Modules

This part is work in progress, too.


### Generating A Python File

Really quickly, if you want to generate Python source code from your grammar,
and perhaps save the source to a file, here's an example:

```python
from sourcer import Grammar

g = Grammar(
    r'''
        start = "Hello" >> @/[a-zA-Z]+/

        ignore Space = @/[ \t]+/
        ignore Punctuation = "," | "." | "!" | "?"
    ''',

    # Add the optional "include_source" flag:
    include_source=True,
)

# The Python code is in the `_source_code` field:
assert 'Space' in g._source_code
```

You can then take the `_source_code` field of your grammar and write it to a
file as part of your build.
