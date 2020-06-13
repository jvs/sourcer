import unittest
from sourcer import *


class TestExpressions(unittest.TestCase):
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
        Space = TokenPattern(r'\s+', is_ignored=True)
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
        Space = TokenPattern(r'\s+', is_ignored=True)
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

    def test_visit_and_transform(self):
        Space = TokenPattern(r'\s+', is_ignored=True)
        Word = TokenPattern(r'[_a-zA-Z][_a-zA-Z0-9]*')
        Symbol = TokenPattern('=')
        Parens = '(' >> Lazy(lambda: Expr) << ')'

        Expr = OperatorPrecedence(
            Word | Parens,
            Prefix('not'),
            LeftAssoc('and'),
            LeftAssoc('or'),
            RightAssoc('implies'),
        )

        class Let(Struct):
            name = Word << '='
            value = Expr

        parser = Parser(start=List(Let | Expr) << End, tokens=[Space, Word, Symbol])
        tree = parser('foo = bar\nfiz implies buz implies zim')

        def find_words(tree):
            words = set()
            for x in visit(tree):
                if isinstance(x, Word):
                    words.add(x.value)
            return words

        self.assertEqual(find_words(tree),
            {'foo', 'bar', 'fiz', 'implies', 'buz', 'zim'})

        def xform(tree):
            return Word(tree.value.upper()) if isinstance(tree, Word) else tree

        other = transform(tree, xform)
        self.assertEqual(find_words(other),
            {'FOO', 'BAR', 'FIZ', 'IMPLIES', 'BUZ', 'ZIM'})

    def test_using_struct_as_token(self):
        Space = TokenPattern(r'\s+', is_ignored=True)
        Word = TokenPattern(r'[_a-zA-Z][_a-zA-Z0-9]*')
        Offset = Regex(r'\d+|\[\-?\d+\]')

        class R1C1Ref(Struct):
            row = 'R' >> Offset
            col = 'C' >> Offset

        class A1Ref(Struct):
            col_mod = Opt('$')
            col = Regex(r'[A-Z]?[A-Z]')
            row_mod = Opt('$')
            row = Regex(r'\d+')

        CellRef = R1C1Ref | A1Ref

        parser = Parser(start=List(CellRef | Word) << End, tokens=[CellRef, Space, Word])
        result = parser('R[11]C[22] implies $AZ33')
        self.assertEqual(result, [
            R1C1Ref(row='[11]', col='[22]'),
            Word('implies'),
            A1Ref(col_mod='$', col='AZ', row_mod=None, row='33'),
        ])

    def test_using_multiple_transforms(self):
        from sourcer.metasyntax import Grammar
        g = Grammar(r'''
            start = Expr << End
            class Expr {
                left: Word
                right: Word
            }
            token Word = `[_a-zA-Z][_a-zA-Z0-9]*`
            ignored token Space = `\s+`
        ''')

        result = g.parse('FOO BAR')

        self.assertEqual(result, g.Expr(
            left=g.Word('FOO'),
            right=g.Word('BAR'),
        ))

        def xform1(tree):
            if isinstance(tree, g.Word):
                return g.Word(tree.value.lower())
            else:
                return tree

        def xform2(tree):
            if isinstance(tree, g.Expr):
                return g.Expr(left=tree.right, right=tree.left)
            else:
                return tree

        other1 = transform(result, xform1, xform2)
        other2 = transform(result, xform2, xform1)
        self.assertEqual(other1, other2)
        self.assertEqual(other1, g.Expr(
            left=g.Word('bar'),
            right=g.Word('foo'),
        ))

    def test_skip_to_expression(self):
        Start = SkipTo('foo') >> 'foo' << End
        result = parse(Start, 'barbazfoo')
        self.assertEqual(result, 'foo')


if __name__ == '__main__':
    unittest.main()
