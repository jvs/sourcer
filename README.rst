sourcer
=======

A pretty simple parsing library for Python.


.. contents::


Why?
----

Sometimes you have to parse things, and sometimes a regex won't cut it.

Things you might have to parse someday:

- log files
- obscure data formats
- spreadsheets
- queries
- user input
- domain specific languages

So that's what this library is for. It's for when you have to take some text
and turn it into some Python objects.


Installation
------------

To install sourcer::

    pip install sourcer

Or download the source from `github <https://github.com/jvs/sourcer>`_
and install with::

    python setup.py install



Examples
--------


Example 1: Hello, World!
~~~~~~~~~~~~~~~~~~~~~~~~

Let's parse the string "Hello, World!" (just to make sure the basics work):

.. code:: python

    from sourcer import Grammar

    g = Grammar(r'''
        start = "Hello" >> Word
        Word = @/[a-zA-Z]+/

        # Ignore whitespace and punctuation.
        ignore Space = @/[ \t]+/
        ignore Punctuaion = "," | "." | "!" | "?"
    ''')

    # Let's try it on the string "Hello, World!"
    person1 = g.parse('Hello, World!')
    assert person1 == 'World'

    # Now let's try some different punctuation.
    person2 = g.parse('Hello Chief?!?!!')
    assert person2 == 'Chief'


Some notes about this example:

* The ``>>`` operator means "Discard the result from the left operand. Just
  return the result from the right operand."
* The ``@/.../`` syntax delimits a regular expression.


Example 2: Parsing JSON
~~~~~~~~~~~~~~~~~~~~~~~

Let's define a grammar for parsing something like (but not exactly like) JSON.

You can use this as a starting point, if you ever need to parse something
similar to JSON.

.. code:: python

    from sourcer import Grammar

    g = Grammar(r'''
        # Import Python modules by quoting your import statement in backticks.
        # (You can also use triple backticks to quote multiple lines.)
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


Example 3: Parsing Arithmetic Expressions
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Here's a quick example showing how to use operator precedence parsing:

.. code:: python

    from sourcer import Grammar

    g = Grammar(r'''
        ignore Space = @/\s+/

        Int = @/\d+/ |> `int`
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

    # Define short names for the constructors.
    I, P, S = g.Infix, g.Prefix, g.Postfix

    result = g.parse('1 + 2')
    assert result == I(1, '+', 2)

    result = g.parse('11 * (22 + 33) - 44 / 55')
    assert result == I(I(11, '*', I(22, '+', 33)), '-', I(44, '/', 55))

    result = g.parse('123 ^ 456')
    assert result == I(123, '^', 456)

    result = g.parse('12 * 34 ^ 56 ^ 78 - 90')
    assert result == I(I(12, '*', I(34, '^', I(56, '^', 78))), '-', 90)

    result = g.parse('12 * 34%')
    assert result == I(12, '*', S(34, '%'))

    result = g.parse('---123')
    assert result == P('-', P('-', P('-', 123)))


Some notes about this example:

* The ``|>`` operator means "Take the result from the left operand and then
  apply the function on the right."
* In this case, the function is simply ``int``.
* So in our example, the ``Int`` rule matches any string of digit characters
  and produces the corresponding ``int`` value.
* So the ``Parens`` rule in our example parses an expression in parentheses,
  discarding the parentheses.
* The ``OperatorPrecedence`` rule constructs the operator precedence table.
  It parses operations and returns ``Operation`` objects.


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

        Start = Opt(Newline) >> (Statement('') // Newline)
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
