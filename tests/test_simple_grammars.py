from sourcer import Grammar


def test_simple_words():
    g = Grammar(r'''
        ignore Space = @/[ \t]+/
        Word = @/[_a-zA-Z][_a-zA-Z0-9]*/
        start = Word*
    ''')

    result = g.parse('foo bar baz')
    assert result == ['foo', 'bar', 'baz']


def test_arithmetic_expressions():
    g = Grammar(r'''
        ignored Space = @/\s+/

        Int = @/\d+/ |> `int`
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

    # Define short names for the constructors.
    I, P = g.Infix, g.Prefix

    result = g.parse('1 + 2')
    assert result == I(1, '+', 2)

    result = g.parse('11 * (22 + 33) - 44 / 55')
    assert result == I(I(11, '*', I(22, '+', 33)), '-', I(44, '/', 55))

    result = g.parse('123 ^ 456')
    assert result == I(123, '^', 456)

    result = g.parse('12 * 34 ^ 56 ^ 78 - 90')
    assert result == I(I(12, '*', I(34, '^', I(56, '^', 78))), '-', 90)

    result = g.parse('---123')
    assert result == P('-', P('-', P('-', 123)))

    result = g.parse('+-12--34++56')
    assert result == I(I(P('+', P('-', 12)), '-', P('-', 34)), '+', P('+', 56))


def test_simple_json_grammar():
    g = Grammar(r'''
        `from ast import literal_eval`

        start = Value

        Value = Object | Array | String | Number | Keyword

        Object = "{" >> (Member // ",") << "}" |> `dict`

        Member = [String << ":", Value]

        Array = "[" >> (Value // ",") << "]"

        String = @/"(?:[^\\"]|\\.)*"/ |> `literal_eval`

        Number = @/-?(?:0|[1-9]\d*)(?:\.\d+)?(?:[eE][+-]?\d+)?/ |> `float`

        Keyword = "true" >> `True` | "false" >> `False` | "null" >> `None`

        ignored Space = @/\s+/
    ''')

    result = g.parse('{"foo": "bar", "baz": true}')
    assert result == {'foo': 'bar', 'baz': True}

    result = g.parse('[12, -34, {"56": 78, "foo": null}]')
    assert result == [12, -34, {'56': 78, 'foo': None}]


def test_many_nested_parentheses():
    g = Grammar(r'start = ["(", start?, ")"]')

    depth = 1001
    text = ('(' * depth) + (')' * depth)
    result = g.parse(text)

    count = 0
    while result:
        assert isinstance(result, list)
        assert len(result) == 3
        assert result[0] == '('
        assert result[2] == ')'
        result = result[1]
        count += 1

    assert count == depth


def test_python_expressions():
    g = Grammar(r'''
        ```
        import ast
        ```

        Expr = (
            @/\d+/ |> `int`
            | @/true/ >> `True`
            | @/false/ >> `False`
            | @/null/ >> `None`
            | @/"([^"\\]|\\.)*"/ |> `ast.literal_eval`
        )
        Space = @/\s+/

        Start = Expr / Space
    ''')
    result = g.parse(r'12 null 34 false 56 "hello:\n\tworld" 78 true')
    assert result == [12, None, 34, False, 56, 'hello:\n\tworld', 78, True]


def test_postfix_operators():
    g = Grammar(r'''
        ignore Space = @/[ \t]+/
        Atom = @/[a-zA-Z]+/

        class ArgList {
            args: "(" >> (Expr / ",") << ")"
        }

        Expr = OperatorPrecedence(
            Atom,
            Postfix(ArgList),
            Postfix("?" | "*" | "+" | "!"),
            LeftAssoc("|"),
        )

        start = Expr
    ''')

    result = g.parse('foo(bar+, baz! | fiz)?')
    assert result == g.Postfix(g.Postfix('foo', g.ArgList([
        g.Postfix('bar', '+'),
        g.Infix(g.Postfix('baz', '!'), '|', 'fiz'),
    ])), '?')


def test_where_expressions():
    g = Grammar(r'''
        start = (Odd | Even)+

        class Odd {
            value: Int where `lambda x: x % 2`
        }

        class Even {
            value: Int where `lambda x: x % 2 == 0`
        }

        Int = @/\d+/ |> `int`

        ignore Space = @/[ \t]+/
    ''')
    result = g.parse('11 22 33 44')
    assert result == [g.Odd(11), g.Even(22), g.Odd(33), g.Even(44)]


def test_expect_and_expect_not_expressions():
    g = Grammar(r'''
        ignore Space = @/[ \t]+/
        Word = @/[_a-zA-Z][_a-zA-Z0-9]*/

        class Angry {
            value: Word << Expect("!")
        }

        class Calm {
            value: Word << ExpectNot("!" | "?")
        }

        class Confused {
            value: Word << Expect("?")
        }

        start = (Angry | Calm | Confused) // ("!" | "?" | "." | ";")
    ''')
    result = g.parse('foo! bar? baz? fiz; buz.')
    assert result == [
        g.Angry('foo'),
        g.Confused('bar'),
        g.Confused('baz'),
        g.Calm('fiz'),
        g.Calm('buz'),
    ]
