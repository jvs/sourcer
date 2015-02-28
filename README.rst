sourcer
=======

Simple parsing library for Python.

There's not much documentation yet, and the performance is probably pretty
bad, but if you want to give it a try, go for it!

Feel free to send me your feedback at vonseg@gmail.com. Or use the github
`issue tracker <https://github.com/jvs/sourcer/issues>`_.

.. contents::


Installation
------------

To install sourcer::

    pip install sourcer

If pip is not installed, use easy_install::

    easy_install sourcer

Or download the source from `github <https://github.com/jvs/sourcer>`_
and install with::

    python setup.py install


Examples
--------


Example 1: Hello, World!
~~~~~~~~~~~~~~~~~~~~~~~~

Let's parse the string "Hello, World!" (just to make sure the basics work):

.. code:: python

    from sourcer import *

    # Let's parse strings like "Hello, foo!", and just keep the "foo" part.
    greeting = 'Hello' >> Opt(',') >> ' ' >> Pattern(r'\w+') << '!'

    # Let's try it on the string "Hello, World!"
    person1 = parse(greeting, 'Hello, World!')
    assert person1 == 'World'

    # Now let's try omitting the comma, since we made it optional (with "Opt").
    person2 = parse(greeting, 'Hello Chief!')
    assert person2 == 'Chief'

Some notes about this example:

* The ``>>`` operator means "Discard the result from the left operand. Just
  return the result from the right operand."
* The ``<<`` operator similarly means "Just return the result from the result
  from the left operand and discard the result from the right operand."
* ``Opt`` means "This term is optional. Parse it if it's there, otherwise just
  keep going."
* ``Pattern`` means "Parse strings that match this regular expression."


Example 2: Parsing Arithmetic Expressions
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Here's a quick example showing how to use operator precedence parsing:

.. code:: python

    from sourcer import *

    Int = Pattern(r'\d+') * int
    Parens = '(' >> ForwardRef(lambda: Expr) << ')'
    Expr = OperatorPrecedence(
        Int | Parens,
        InfixRight('^'),
        Prefix('+', '-'),
        Postfix('%'),
        InfixLeft('*', '/'),
        InfixLeft('+', '-'),
    )

    # Now let's try parsing an expression.
    t1 = parse(Expr, '1+2^3/4')
    assert t1 == Operation(1, '+', Operation(Operation(2, '^', 3), '/', 4))

    # Let's try putting some parentheses in the next one.
    t2 = parse(Expr, '1*(2+3)')
    assert t2 == Operation(1, '*', Operation(2, '+', 3))

    # Finally, let's try using a unary operator in our expression.
    t3 = parse(Expr, '-1*2')
    assert t3 == Operation(Operation(None, '-', 1), '*', 2)

Some notes about this example:

* The ``*`` operator means "Take the result from the left operand and then
  apply the function on the right."
* In this case, the function is simply ``int``.
* So in our example, the ``Int`` rule matches any string of digit characters
  and produces the corresponding ``int`` value.
* So the ``Parens`` rule in our example parses an expression in parentheses,
  discarding the parentheses.
* The ``ForwardRef`` term is necessary because the ``Parens`` rule wants to
  refer to the ``Expr`` rule, but ``Expr`` hasn't been defined by that point.
* The ``OperatorPrecedence`` rule constructs the operator precedence table.
  It parses operations and returns ``Operation`` objects.


Example 3: Building an Abstract Syntax Tree
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Let's try building a simple AST for the
`lambda calculus <http://en.wikipedia.org/wiki/Lambda_calculus>`_. We can use
``Struct`` classes to define the AST and the parser at the same time:

.. code:: python

    from sourcer import *

    class Identifier(Struct):
        def parse(self):
            self.name = Word

    class Abstraction(Struct):
        def parse(self):
            self.parameter = '\\' >> Word
            self.body = '. ' >> Expr

    class Application(LeftAssoc):
        def parse(self):
            self.left = Operand
            self.operator = ' '
            self.right = Operand

    Word = Pattern(r'\w+')
    Parens = '(' >> ForwardRef(lambda: Expr) << ')'
    Operand = Parens | Abstraction | Identifier
    Expr = Application | Operand

    t1 = parse(Expr, r'(\x. x) y')
    assert isinstance(t1, Application)
    assert isinstance(t1.left, Abstraction)
    assert isinstance(t1.right, Identifier)
    assert t1.left.parameter == 'x'
    assert t1.left.body.name == 'x'
    assert t1.right.name == 'y'

    t2 = parse(Expr, 'x y z')
    assert isinstance(t2, Application)
    assert isinstance(t2.left, Application)
    assert isinstance(t2.right, Identifier)
    assert t2.left.left.name == 'x'
    assert t2.left.right.name == 'y'
    assert t2.right.name == 'z'


Example 4: Tokenizing
~~~~~~~~~~~~~~~~~~~~~

It's often useful to tokenize your input before parsing it. Let's create a
tokenizer for the lambda calculus.

.. code:: python

    from sourcer import *

    class LambdaTokens(TokenSyntax):
        def __init__(self):
            self.Word = r'\w+'
            self.Symbol = AnyChar(r'(\.)')
            self.Space = Skip(r'\s+')

    # Run the tokenizer on a lambda term with a bunch of random whitespace.
    Tokens = LambdaTokens()
    ans1 = tokenize(Tokens, '\n (   x  y\n\t) ')

    # Assert that we didn't get any space tokens.
    assert len(ans1) == 4
    (t1, t2, t3, t4) = ans1
    assert isinstance(t1, Tokens.Symbol) and t1.content == '('
    assert isinstance(t2, Tokens.Word) and t2.content == 'x'
    assert isinstance(t3, Tokens.Word) and t3.content == 'y'
    assert isinstance(t4, Tokens.Symbol) and t4.content == ')'

    # Let's use the tokenizer with a simple grammar, just to show how that
    # works.
    Sentence = Some(Tokens.Word) << '.'
    ans2 = tokenize_and_parse(Tokens, Sentence, 'This is a test.')

    # Assert that we got a list of Word tokens.
    assert all(isinstance(i, Tokens.Word) for i in ans2)

    # Assert that the tokens have the expected content.
    contents = [i.content for i in ans2]
    assert contents == ['This', 'is', 'a', 'test']


In this example, the ``Skip`` term tells the tokenizer that we want to ignore
whitespace. The ``AnyChar`` term tell the tokenizer that a symbol can be any
one of the characters ``(``, ``\``, ``.``, ``)``. Alternatively, we could have
used:

.. code:: python

    Symbol = r'[(\\.)]'


Example 5: Parsing Significant Indentation
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

We can use sourcer to parse languages with significant indentation. Here's a
bare-bones example to demonstrate one possible approach.

.. code:: python

    from sourcer import *

    class TestTokens(TokenSyntax):
        def __init__(self):
            # Let's just use words, newlines, and spaces in this example.
            self.Word = r'\w+'
            self.Newline = r'\n'
            # In this case, we'll say that an indent is a newline followed by
            # some spaces, followed by a word.
            self.Indent = r'(?<=\n) +(?=\w)'
            # And let's just throw out all other space characters.
            self.Space = Skip(' +')

    # All our token classes are attributes of this ``Tokens`` object. It's
    # essentially a namespace for our token classes.
    Tokens = TestTokens()

    class InlineStatement(Struct):
        def parse(self):
            # Let's say an inline-statement is just some word tokens. We'll use
            # ``Content`` to get the string content of each token (since in this
            # case, we don't care about the tokens themselves).
            self.words = Some(Content(Tokens.Word))

        def __repr__(self):
            # We'll define a ``repr`` method so that we can easily check the
            # parse results. We'll just put a semicolon after each statement.
            return '%s;' % ' '.join(self.words)

    class Block(Struct):
        def parse(self, indent=''):
            # A block is a bunch of statements at the same indentation,
            # all separated by some newline tokens.
            self.statements = Statement(indent) // Some(Tokens.Newline)

        def __repr__(self):
            # In this case, we'll put a space between each statement and enclose
            # the whole block in curly braces. This will make it easy for us to
            # tell if our parse results look right.
            return '{%s}' % ' '.join(repr(i) for i in self.statements)

    def Statement(indent):
        # Let's say there are two ways to get a statement:
        # - Get an inline-statement with the current indentation.
        # - Get a block that is indented farther than the current indentation.
        return (CurrentIndent(indent) >> InlineStatement
            | IncreaseIndent(indent) ** Block)

    def CurrentIndent(indent):
        # The point of this function is to return a parsing expression that
        # matches the current indent (which is provided as an argument).

        # If the current indent is the empty string, then we don't need to
        # consume any input. (We don't have tokens for zero-indentation.)
        return None if indent == '' else indent

    def IncreaseIndent(current):
        # To see if the next indentation is more than the current indentation,
        # we peek at the next token, using ``Expect``, and we get its string
        # content using ``Content``. The ``^`` operator means "require". In this
        # case, we require that the next indentation is longer than the current
        # indentation.
        token = Expect(Content(Tokens.Indent))
        return token ^ (lambda token: len(current) < len(token))

    # Let's say that a program is a block, optionally surrounded by newlines.
    # (The ``>>`` and ``<<`` operators discard the newlines in this case.)
    OptNewlines = List(Tokens.Newline)
    Program = OptNewlines >> Block << OptNewlines

    test = '''
    print foo
    while true
        print bar
        if baz
            then break
    exit
    '''

    # Let's parse the test case and then use ``repr`` to make sure that we get
    # back what we expect.
    ans = tokenize_and_parse(Tokens, Program, test)
    expect = '{print foo; while true; {print bar; if baz; {then break;}} exit;}'
    assert repr(ans) == expect


More Examples
-------------
Parsing `Excel formula <https://github.com/jvs/sourcer/tree/master/examples>`_
and some corresponding
`test cases <https://github.com/jvs/sourcer/blob/master/tests/test_excel.py>`_.
