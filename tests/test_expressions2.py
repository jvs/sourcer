import unittest
from sourcer.expressions2 import *


class TestExpression2(unittest.TestCase):
    def test_simple_alernation(self):
        Word = TokenPattern(r'[_a-zA-Z][_a-zA-Z0-9]*')
        Comma = TokenPattern(r'\s*,\s*')

        # Try parsing a simple list of words separated by commas.
        Words = Alt(Word, Comma) << End
        result = parse(Words, 'foo, bar , baz')
        self.assertEqual(result, [
            Word('foo'),
            Word('bar'),
            Word('baz'),
        ])

        # Try adding a trailing comma to the input text.
        with self.assertRaises(ParseError):
            parse(Alt(Word, Comma) << End, 'foo, bar, baz,')

        # Try allowing the trailing comma this time.
        Words = Alt(Word, Comma, allow_trailer=True) << End
        result = parse(Words, 'foo, bar, baz,')
        self.assertEqual(result, [
            Word('foo'),
            Word('bar'),
            Word('baz'),
        ])

    def test_empty_alternation(self):
        Letters = '(' >> Alt('A', ',') << ')' << End
        result = parse(Letters, '()')
        self.assertEqual(result, [])

    def test_some_simple_any_expressions(self):
        # Accept a list of any character.
        Elements = List(Any) << End
        result = parse(Elements, 'ABC')
        self.assertEqual(result, ['A', 'B', 'C'])

        # Try it on the empty string.
        result = parse(Elements, '')
        self.assertEqual(result, [])

        # Try it on a list of numbers.
        result = parse(Elements, [1, 2, 3])
        self.assertEqual(result, [1, 2, 3])

        # Make sure the Any expression fails when the input text is empty.
        with self.assertRaises(ParseError):
            parse(Any, '')

        with self.assertRaises(ParseError):
            parse(Any, [])

    def test_simple_choice_expressions(self):
        Int = Regex(r'[0-9]+') * int
        Word = TokenPattern(r'[_a-zA-Z][_a-zA-Z0-9]*')
        Number = TokenClass(Int)
        Comma = TokenPattern(r'\s*,\s*')
        Elements = ((Word | Number) / Comma) << End

        result = parse(Elements, 'foo, 10, bar, 25, 50, baz')
        self.assertEqual(result, [
            Word('foo'),
            Number(10),
            Word('bar'),
            Number(25),
            Number(50),
            Word('baz'),
        ])

    def test_simple_struct(self):
        Space = TokenPattern(r'\s+', is_dropped=True)
        Word = TokenPattern(r'[_a-zA-Z][_a-zA-Z0-9]*')

        class If(Struct):
            if_ = 'if' >> Word
            then_ = 'then' >> Word
            else_ = 'else' >> Word

        parser = Parser(start=If << End, tokens=[Space, Word])

        result = parser('if foo then bar else baz')
        self.assertEqual(result, If(
            if_=Word('foo'),
            then_=Word('bar'),
            else_=Word('baz'),
        ))

        # Sanity-check the basic parts.
        self.assertIsInstance(result, If)
        self.assertEqual(result.if_, Word('foo'))
        self.assertEqual(result.then_, Word('bar'))
        self.assertEqual(result.else_, Word('baz'))

        # Sanity-check the utilities.
        self.assertEqual(result._fields, ('if_', 'then_', 'else_'))
        self.assertEqual(result._asdict(), {
            'if_': Word('foo'),
            'then_': Word('bar'),
            'else_': Word('baz'),
        })


if __name__ == '__main__':
    unittest.main()
