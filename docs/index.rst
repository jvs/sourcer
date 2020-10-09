.. Sourcer documentation master file, created by
   sphinx-quickstart on Wed Oct  7 18:39:27 2020.
   You can adapt this file completely to your liking, but it should at least
   contain the root `toctree` directive.

Sourcer Documentation
=====================

Sourcer is a parsing library for Python.


Hello, World
------------

.. code:: python

   from sourcer import Grammar

   g = Grammar(r'''
      start = "Hello" >> /[a-zA-Z]+/

      # Ignore whitespace and punctuation.
      ignore /[ \t]+/
      ignore "," | "." | "!" | "?"
   ''')

   assert g.parse('Hello, World!') == 'World'
   assert g.parse('Hello?! Anybody?!') == 'Anybody'


Notes:

* ``>>`` means "discard the the left hand side"
* ``/.../`` means "regular expression"


Installation
============

Use pip:

.. code:: bash

   $ pip install sourcer

Notes:

* Sourcer is a pure Python library, with no dependencies beyond the standard library.
* Sourcer requires Python version 3.6 or later.


Quickstart
==========

If you're in a hurry, first make sure :ref:`Hello, World` works (shown above).
Then take a look at the examples, and see if you can copy one and start from
there.

As you build up your grammar, try to test it each step of the way.

Two things to keep in mind:

1. In Sourcer, the ``|`` operator represents ordered choice.
  So for example if you have an expression like ``(">" | ">=")``, it will never
  actually match ``">="``, because the ``">"`` will always match first.

.. code:: python

   from sourcer import Grammar

   g = Grammar('start = ["foo", ">" | ">=",  "bar"]')

   assert g.parse('foo>bar') == ['foo', '>', 'bar']

   try:
      g.parse("foo>=bar")
      assert False
   except g.ParseError:
      pass

   h = Grammar('start = ["foo", ">=" | ">",  "bar"]')
   assert h.parse('foo>=bar') == ['foo', '>=', 'bar']


2. Sourcer grammars work on strings, not tokens. So for example if you an
  expression like ``"hi" >> /\w+/``, it will match the string ``'highlight'``
  and return ``'ghlight'``.

.. code:: python

   from sourcer import Grammar

   g = Grammar('start = "hi" >> /\w+/")
   assert g.parse('highlight') == 'ghlight'


Write tests to make sure the Sourcer is actually doing what you want.


.. toctree::
   :maxdepth: 2
   :caption: Examples
   :hidden:
   :glob:

   examples/*


.. toctree::
   :maxdepth: 3
   :caption: Parsing Expressions
   :hidden:
   :glob:

   expressions/*
