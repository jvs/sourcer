import unittest
from sourcer.expressions2 import *


class TestExpressions2(unittest.TestCase):
    def test_many_nested_parentheses(self):
        Bal = Lazy(lambda: Balanced)
        Balanced = End | Seq('(', Opt(Bal), ')', Opt(Bal))
        depth = 1001
        text = ('(' * depth) + (')' * depth)
        result = parse(Balanced << End, text)

        count = 0
        while result:
            assert isinstance(result, list)
            assert len(result) == 4
            assert result[0] == '('
            assert result[2] == ')'
            assert result[3] is None
            result = result[1]
            count += 1

        self.assertEqual(count, depth)

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
        Word = TokenPattern(r'[_a-zA-Z][_a-zA-Z0-9]*')
        Number = TokenClass(Regex(r'[0-9]+') * int)
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

    def test_simple_operator_precedence(self):
        Space = TokenPattern(r'\s+', is_dropped=True)
        Word = TokenPattern(r'[_a-zA-Z][_a-zA-Z0-9]*')
        Number = TokenClass(Regex(r'[0-9]+') * int)
        Symbol = TokenPattern(r'[\+\-\*\/\(\)\%\^]')
        Parens = '(' >> Lazy(lambda: Expr) << ')'

        Expr = OperatorPrecedence(
            Word | Number | Parens,
            Prefix(Choice('+', '-')),
            Postfix('%'),
            RightAssoc('^'),
            LeftAssoc(Choice('*', '/')),
            LeftAssoc(Choice('+', '-')),
        )

        parser = Parser(start=Expr, tokens=[Space, Word, Number, Symbol])

        # Short names.
        N = Number
        S = Symbol
        In = InfixOp
        Pr = PrefixOp
        Ps = PostfixOp

        result = parser('1 + 2 * 3')
        self.assertEqual(result, In(N(1), S('+'), In(N(2), S('*'), N(3))))

        result = parser('1 + 2 ^ -3 ^ 4 / 5%')
        self.assertEqual(result,
            In(
                N(1),
                S('+'),
                In(
                    In(
                        N(2),
                        S('^'),
                        In(
                            Pr(S('-'), N(3)),
                            S('^'),
                            N(4),
                        ),
                    ),
                    S('/'),
                    Ps(N(5), S('%')),
                )
            )
        )


if __name__ == '__main__':
    unittest.main()
