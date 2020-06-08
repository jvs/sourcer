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
        self.assertEqual(tree._asdict(), {
            'bar': 'bar',
            'baz': 'zim',
        })


if __name__ == '__main__':
    unittest.main()
