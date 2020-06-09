import unittest

from sourcer.metasyntax import Grammar


class TestMetasyntax(unittest.TestCase):
    def test_simple_grammar(self):
        grammar = Grammar('''
            Name = "foo" | "bar" | "baz"
            start = Name / ","
        ''')
        tree = grammar.parse('baz,foo,bar')
        self.assertEqual(tree, ['baz', 'foo', 'bar'])

    def test_simple_grammar_with_class(self):
        grammar = Grammar('''
            class Foo {
                bar = "bar"?
                baz = `baz|zim`
            }
            start = Foo
        ''')
        tree = grammar.parse('barzim')
        self.assertIsInstance(tree, grammar.Foo)
        self.assertEqual(tree, grammar.Foo(bar='bar', baz='zim'))
        self.assertEqual(tree._asdict(), {'bar': 'bar', 'baz': 'zim'})

    def test_grammar_with_operator_precedence(self):
        g = Grammar(r'''
            start = Expr

            Expr = OperatorPrecedence(
                Word | Number | Parens,
                Prefix('+' | '-'),
                RightAssoc('^'),
                LeftAssoc('*' | '/'),
                LeftAssoc('+' | '-'),
            )

            Word = Token(`[_a-zA-Z][_a-zA-Z0-9]*`)
            Number = Token(`[0-9]+`)
            Parens = '(' >> Expr << ')'

            Symbol = Token(`[\+\-\*\/\(\)\%\^]`)
            Space = Token(`\s+`, True)
        ''')
        tree = g.parse('1 * (2 + 3) - four / 5')
        self.assertEqual(tree, g.InfixOp(
            g.InfixOp(
                g.Number('1'),
                g.Symbol('*'),
                g.InfixOp(
                    g.Number('2'),
                    g.Symbol('+'),
                    g.Number('3'),
                ),
            ),
            g.Symbol('-'),
            g.InfixOp(
                g.Word('four'),
                g.Symbol('/'),
                g.Number('5'),
            ),
        ))


if __name__ == '__main__':
    unittest.main()
