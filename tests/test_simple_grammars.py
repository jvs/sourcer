from sourcer import Grammar


def test_simple_words():
    g = Grammar(r'''
        ignored token Space = `[ \t]+`
        token Word = `[_a-zA-Z][_a-zA-Z0-9]*`
        start = Word*
    ''')

    result = g.parse('foo bar baz')
    assert result == [g.Word('foo'), g.Word('bar'), g.Word('baz')]


def test_arithmetic_expressions():
    g = Grammar(r'''
        # Tokens:
        ignored token Space = `\s+`
        token Int = `\d+`
        token Symbol = `[\+\-\*\/\(\)\^]`

        # Expressions:
        Parens = '(' >> Expr << ')'
        Expr = OperatorPrecedence(
            Int | Parens,
            Prefix('+' | '-'),
            RightAssoc('^'),
            LeftAssoc('*' | '/'),
            LeftAssoc('+' | '-'),
        )
        start = Expr
    ''')

    result = g.parse('1 + 2')
    assert result == g.Infix(g.Int('1'), g.Symbol('+'), g.Int('2'))

    result = g.parse('11 * (22 + 33) - 44 / 55')
    assert result == g.Infix(
        g.Infix(
            g.Int('11'),
            g.Symbol('*'),
            g.Infix(
                g.Int('22'),
                g.Symbol('+'),
                g.Int('33'),
            ),
        ),
        g.Symbol('-'),
        g.Infix(
            g.Int('44'),
            g.Symbol('/'),
            g.Int('55'),
        ),
    )
