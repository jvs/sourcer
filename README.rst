sourcer
=======

Simple parsing library for Python.

There's not much documentation yet, and the performance is probably pretty
bad, but if you want to give it a try, go for it!

Feel free to send me your feedback at vonseg@gmail.com. Or use the github
`issue tracker <https://github.com/jvs/sourcer/issues>`_.


Installation
------------

To install sourcer::

    pip install sourcer

If pip is not installed, use easy_install::

    easy_install sourcer

Or download the source from `github <https://github.com/jvs/sourcer>`_
and install with::

    python setup.py install


Example: Hello, World!
---------------------------------------

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


Example: Parsing Arithmetic Expressions
---------------------------------------

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
    tree1 = parse(Expr, '1+2^3/4')
    assert tree1 == Operation(1, '+', Operation(Operation(2, '^', 3), '/', 4))

    # Let's try putting some parentheses in the next one.
    tree2 = parse(Expr, '1*(2+3)')
    assert tree2 == Operation(1, '*', Operation(2, '+', 3))

    # Finally, let's try using a unary operator in our expression.
    tree3 = parse(Expr, '-1*2')
    assert tree3 == Operation(Operation(None, '-', 1), '*', 2)

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


Example: Building an Abstract Syntax Tree
-----------------------------------------

Let's try building a simple AST for the
`lambda calculus <http://en.wikipedia.org/wiki/Lambda_calculus>`_. We can use
``Struct`` classes to define the AST and the parser at the same time:

.. code:: python

    from sourcer import *

    class Identifier(Struct):
        def __init__(self):
            self.name = Word

        def __repr__(self):
            return self.name

    class Abstraction(Struct):
        def __init__(self):
            self.parameter = '\\' >> Word
            self.body = '. ' >> Expr

        def __repr__(self):
            return r'(\%s. %r)' % (self.parameter, self.body)

    class Application(LeftAssoc):
        def __init__(self):
            self.left = Operand << ' '
            self.right = Operand

        def __repr__(self):
            return '%r %r' % (self.left, self.right)

    Word = Pattern(r'\w+')
    Parens = '(' >> ForwardRef(lambda: Expr) << ')'
    Operand = Parens | Abstraction | Identifier
    Expr = Application | Operand

    tree = parse(Expr, r'(\x. x) y')
    assert isinstance(tree, Application)
    assert isinstance(tree.left, Abstraction)
    assert isinstance(tree.right, Identifier)
    assert repr(tree.left) == r'(\x. x)'
    assert repr(tree.right) == 'y'


More Examples
-------------
Parsing `Excel formula <https://github.com/jvs/sourcer/tree/master/examples>`_
and some corresponding
`test cases <https://github.com/jvs/sourcer/blob/master/tests/test_excel.py>`_.
