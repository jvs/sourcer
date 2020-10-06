sourcer
=======

A parsing library for Python (version 3.6 and later).


.. contents::


Installation
------------

To install sourcer::

    pip install sourcer

Or download the source from `github <https://github.com/jvs/sourcer>`_
and install with::

    python setup.py install


Hello $World example
~~~~~~~~~~~~~~~~~~~~

.. code:: python

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


Some notes about this example:

* The ``>>`` operator means "Parse and then discard the the left hand side."
* The ``@/.../`` syntax delimits a regular expression.


Why?
----

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


**Aren't there a ton of other parsing libraries for Python?**

Yes. If you need to parse something, try a few different libraries and see which
one you like best.



Features
~~~~~~~~

- Supports Python version 3.6 and later.
- Create parsers at runtime, or generate Python source code as part of your build.
- Implements `Parsing Expression Grammars <http://en.wikipedia.org/wiki/Parsing_expression_grammar>`
  (where "|" represents ordered choice).
- Built-in support for operator precedence parsing.
- Supports Python expressions, for defining predicates and transformations
  directly within grammars.
- Supports class definitions for defining the structure of your parse trees.
- Each rule in a grammar becomes a top-level function in the generated Python
  module, so you can use a grammar as a parsing library, rather than just a
  monolithic "parse" function.
- Supports data dependent rules, for things like:

    - significant indentation.
    - matching start and end tags.


Examples
--------


Example 1: Something Like JSON
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Maybe you have to parse something that is a little bit like JSON, but different
enough that you can't use a real JSON parser. Here's a simple example that you
can start with and work from, and build it up into what you need:

.. code:: python

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
        # curly braces. Convert objects to Python dicts.
        Object = "{" >> (Member // ",") << "}" |> `dict`

        # A member is a pair of string literal and value, separated by a colon.
        Member = [String << ":", Value]

        # An array is zero or more values separated by commas, enclosed in
        # square braces. Convert arrays to Python lists.
        Array = "[" >> (Value // ",") << "]"

        # Interpret each string as a Python literal string.
        String = @/"(?:[^\\"]|\\.)*"/ |> `literal_eval`

        # Interpret each number as a Python float literal.
        Number = @/-?(?:0|[1-9]\d*)(?:\.\d+)?(?:[eE][+-]?\d+)?/ |> `float`

        # Convert boolean literals to Python booleans, and "null" to None.
        Keyword = "true" >> `True` | "false" >> `False` | "null" >> `None`

        ignored Space = @/\s+/
    ''')

    result = g.parse('{"foo": "bar", "baz": true}')
    assert result == {'foo': 'bar', 'baz': True}

    result = g.parse('[12, -34, {"56": 78, "foo": null}]')
    assert result == [12, -34, {'56': 78, 'foo': None}]


Example 2: Arithmetic Expressions
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Here's a barebones grammar for arithmetic expressions. You can build it up with
your own operators, if you have to parse some kind of specialized equations.

.. code:: python

    from sourcer import Grammar

    g = Grammar(r'''
        ignore Space = @/\s+/

        # Turn integers into Python int objects.
        Int = @/\d+/ |> `int`

        # Discard parentheses, so that they don't show up in the result.
        Parens = '(' >> Expr << ')'

        Expr = OperatorPrecedence(
            Int | Parens,
            Prefix('+' | '-'),
            RightAssoc('^'),
            Postfix('%'),
            LeftAssoc('*' | '/'),
            LeftAssoc('+' | '-'),
        )
        start = Expr
    ''')

    # Simple addition:
    result = g.parse('1 + 2')
    assert result == g.Infix(1, '+', 2)

    # Left associativity:
    result = g.parse('1 + 2 + 3')
    assert result == g.Infix(g.Infix(1, '+', 2), '+', 3)

    # Postfix operator:
    result = g.parse('12 * 34%')
    assert result == g.Infix(12, '*', g.Postfix(34, '%'))

    # Operator precedence:
    result = g.parse('4 + -5 / 6')
    assert result == g.Infix(4, '+', g.Infix(g.Prefix('-', 5), '/', 6))

    # Parentheses:
    result = g.parse('7 * (8 + 9)')
    assert result == g.Infix(7, '*', g.Infix(8, '+', 9))

    # Right associativity:
    result = g.parse('10 ^ 11 ^ 12')
    assert result == g.Infix(10, '^', g.Infix(11, '^', 12))


Some notes about this example:

* The ``|>`` operator means "Take the result from the left operand and then
  apply the function on the right."
* The ``OperatorPrecedence`` rule constructs the operator precedence table.
  It parses operations and returns ``Infix``, ``Prefix``, and ``Postfix`` objects.



Example 3: Using Classes
~~~~~~~~~~~~~~~~~~~~~~~~

This is just a quick example to show how you can define classes within your
grammars.

.. code:: python

    from sourcer import Grammar

    g = Grammar(r'''
        # Parse a list of commands separated by semicolons.
        start = Command / ";"

        # A command is an action and a range.
        class Command {
            action: "Copy" | "Delete" | "Print"
            range: Range
        }

        # A range can be open or closed on either end.
        class Range {
            open: "(" | "["
            left: Int << ","
            right: Int
            close: "]" | ")"
        }

        Int = @/\d+/ |> `int`

        ignore Space = @/\s+/
    ''')

    result = g.parse('Print [10, 20); Delete (33, 44);')
    assert result == [
        g.Command(
            action='Print',
            range=g.Range('[', 10, 20, ')')
        ),
        g.Command(
            action='Delete',
            range=g.Range('(', 33, 44, ')')
        ),
    ]

    # Objects created from these classes have position information:
    assert result[1]._position_info.start == g._Position(
        index=16, line=1, column=17,
    )

    assert result[1]._position_info.end == g._Position(
        index=30, line=1, column=31,
    )



Example 4: Parsing Significant Indentation
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

If you ever need to parse something with significant indentation, you can start
with this example.

.. code:: python

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


More Examples
-------------
Parsing `Excel formula <https://github.com/jvs/sourcer/tree/master/examples>`_
and some corresponding
`test cases <https://github.com/jvs/sourcer/blob/master/tests/test_excel.py>`_.


Background
----------
`Parsing expression grammar
<http://en.wikipedia.org/wiki/Parsing_expression_grammar>`_.
