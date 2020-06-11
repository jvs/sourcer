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

    def test_simple_grammar_with_a_token_class(self):
        g = Grammar('''
            start = Any* << End
            token class HyphenatedWord {
                left = Word
                right = Commit("-") >> Word
            }
            token Word = `[_a-zA-Z][_a-zA-Z0-9]*`
            token Hyphen = "-"

            ignored token Space = " "
        ''')
        result = g.parse('foo-bar and fiz-buz now')
        self.assertEqual(result, [
            g.HyphenatedWord(left=g.Word('foo'), right=g.Word('bar')),
            g.Word('and'),
            g.HyphenatedWord(left=g.Word('fiz'), right=g.Word('buz')),
            g.Word('now'),
        ])

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

            Parens = '(' >> Expr << ')'

            token Word = `[_a-zA-Z][_a-zA-Z0-9]*`
            token Number = `[0-9]+`
            token Symbol = `[\+\-\*\/\(\)\%\^]`

            ignored token Space = `\s+`
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

    def test_simple_template(self):
        g = Grammar('''
            start = Term

            template wrap(a, b) = b >> a << b
            template extend(x) = wrap(x, Newline?)

            Term = Word / extend(Cont)

            token Word = `[_a-zA-Z][_a-zA-Z0-9]*`
            token Cont = `\-`
            token Newline = `\n+`

            ignored token Space = `\s+`
        ''')
        result = g.parse('foo - bar \n - \n baz')
        self.assertEqual(result, [g.Word('foo'), g.Word('bar'), g.Word('baz')])


if __name__ == '__main__':
    unittest.main()
