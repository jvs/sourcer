import pytest
from textwrap import dedent
from sourcer import Grammar


def test_simple_words():
    g = Grammar(r'''
        ignore Space = /[ \t]+/
        Word = /[_a-zA-Z][_a-zA-Z0-9]*/
        start = Word*
    ''')

    result = g.parse('foo bar baz')
    assert result == ['foo', 'bar', 'baz']


def test_arithmetic_expressions():
    g = Grammar(r'''
        ignored Space = /\s+/

        Int = /\d+/ |> `int`
        Parens = '(' >> Expr << ')'

        Expr = OperatorPrecedence(
            Int | Parens,
            Prefix('+' | '-'),
            RightAssoc('^'),
            Postfix('%'),
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

    # Right associativity:
    result = g.parse('10 ^ 11 ^ 12')
    assert result == g.Infix(10, '^', g.Infix(11, '^', 12))

    # Postfix operator:
    result = g.parse('12 * 34%')
    assert result == g.Infix(12, '*', g.Postfix(34, '%'))


def test_simple_json_grammar():
    g = Grammar(r'''
        `from ast import literal_eval`

        start = Value

        Value = Object | Array | String | Number | Keyword

        Object = "{" >> (Member // ",") << "}" |> `dict`

        Member = [String << ":", Value]

        Array = "[" >> (Value // ",") << "]"

        String = /"(?:[^\\"]|\\.)*"/ |> `literal_eval`

        Number = /-?(?:0|[1-9]\d*)(?:\.\d+)?(?:[eE][+-]?\d+)?/ |> `float`

        Keyword = "true" >> `True` | "false" >> `False` | "null" >> `None`

        ignored Space = /\s+/
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
            /\d+/ |> `int`
            | /true/ >> `True`
            | /false/ >> `False`
            | /null/ >> `None`
            | /"([^"\\]|\\.)*"/ |> `ast.literal_eval`
        )
        Space = /\s+/

        Start = Expr /? Space
    ''')
    result = g.parse(r'12 null 34 false 56 "hello:\n\tworld" 78 true')
    assert result == [12, None, 34, False, 56, 'hello:\n\tworld', 78, True]


def test_postfix_operators():
    g = Grammar(r'''
        ignore Space = /[ \t]+/
        Atom = /[a-zA-Z]+/

        class ArgList {
            args: "(" >> (Expr /? ",") << ")"
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

        Int = /\d+/ |> `int`

        ignore Space = /[ \t]+/
    ''')
    result = g.parse('11 22 33 44')
    assert result == [g.Odd(11), g.Even(22), g.Odd(33), g.Even(44)]


def test_expect_and_expect_not_expressions():
    g = Grammar(r'''
        ignore Space = /[ \t]+/
        Word = /[_a-zA-Z][_a-zA-Z0-9]*/

        class Angry {
            value: Word << Expect("!")
        }

        class Calm {
            value: Word << ExpectNot("!" | "?")
        }

        class Confused {
            value: Word << Expect("?")
        }

        start = (Angry | Calm | Confused) /? ("!" | "?" | "." | ";")
    ''')
    result = g.parse('foo! bar? baz? fiz; buz.')
    assert result == [
        g.Angry('foo'),
        g.Confused('bar'),
        g.Confused('baz'),
        g.Calm('fiz'),
        g.Calm('buz'),
    ]


def test_simple_data_dependent_class():
    g = Grammar(r'''
        class Element {
            open_tag: "<" >> Word << ">"
            content: Item*
            close_tag: "</" >> Word << ">" where `lambda x: x == open_tag`
        }

        class Text {
            content: /[^<]+/
        }

        Item = Element | Text

        Word = /[_a-zA-Z][_a-zA-Z0-9]*/

        start = Item+
    ''')
    result = g.parse('foo <bar>baz <zim>zam</zim> fiz</bar> buz')
    assert result == [
        g.Text('foo '),
        g.Element('bar', [
            g.Text('baz '),
            g.Element('zim', [g.Text('zam')], 'zim'),
            g.Text(' fiz'),
        ], 'bar'),
        g.Text(' buz'),
    ]


def test_simple_rule_with_parameter():
    g = Grammar(r'''
        ignored Space = /[ \t]+/
        Name = /[_a-zA-Z][_a-zA-Z0-9]*/
        Pair(x) = "(" >> [x << ",", x] << ")"

        class Range {
            start: Name << "to"
            stop: Name
        }

        start = Pair(Range | "ok")
    ''')
    result = g.parse('(foo to bar, fiz to buz)')
    assert result == [g.Range('foo', 'bar'), g.Range('fiz', 'buz')]

    result = g.parse('(ok, ok)')
    assert result == ['ok', 'ok']


def test_simple_class_with_parameters():
    g = Grammar(r'''
        ignored Space = /[ \t]+/

        Name = /[_a-zA-Z][_a-zA-Z0-9]*/
        Int = /\d+/ |> `int`

        class Pair(A, B) {
            first: A << "&"
            second: B
        }

        Names = "[" >> (Name /? ",") << "]"
        Ints = "[" >> (Int /? ",") << "]"
        Start = Pair(Names, Ints)
    ''')
    result = g.parse('[foo, bar, baz] & [11, 22, 33]')
    assert result == g.Pair(['foo', 'bar', 'baz'], [11, 22, 33])


def test_simplified_indentation():
    g = Grammar(r'''
        ignore Space = /[ \t]+/

        Indent = /\n[ \t]*/

        MatchIndent(i) =>
            Indent where `lambda x: x == i`

        IncreaseIndent(i) =>
            Indent where `lambda x: len(x) > len(i)`

        Body(current_indent) =>
            let i = IncreaseIndent(current_indent) in
            Statement(i) // MatchIndent(i)

        Statement(current_indent) =>
            If(current_indent) | Print

        class If(current_indent) {
            test: "if" >> Name
            body: Body(current_indent)
        }

        class Print {
            name: "print" >> Name
        }

        Name = /[a-zA-Z]+/
        Newline = /[\r\n]+/

        Start = Opt(Newline) >> (Statement('') /? Newline)
    ''')

    result = g.parse('print ok\nprint bye')
    assert result == [g.Print('ok'), g.Print('bye')]

    result = g.parse('if foo\n  print bar')
    assert result == [g.If('foo', [g.Print('bar')])]

    result = g.parse(dedent('''
        print ok
        if foo
            if bar
                print baz
                print fiz
            print buz
        print zim
    '''))
    assert result == [
        g.Print('ok'),
        g.If('foo', [
            g.If('bar', [
                g.Print('baz'),
                g.Print('fiz'),
            ]),
            g.Print('buz'),
        ]),
        g.Print('zim'),
    ]


def test_passing_pythons_max_block_depth():
    buf = ['start = ']
    depth = 100

    for i in range(depth):
        buf.append(f'[Opt("S{depth - i - 1}"), ')

    buf.append('"T"')
    buf.append(']' * depth)

    g = Grammar(''.join(buf))

    result = g.parse('T')

    count = 0
    while isinstance(result, list) and len(result) == 2:
        count += 1
        result = result[-1]

    assert result == 'T' and count == 100


def test_case_insensitivity():
    g = Grammar(r'''
        hi = "hi"
        hello = "hello"i
        command = /copy|delete|print/i
    ''')

    result = g.hi.parse('hi')
    assert result == 'hi'

    with pytest.raises(Exception):
        g.hi.parse('HI')

    result = g.hello.parse('Hello')
    assert result == 'Hello'

    result = g.hello.parse('HELLO')
    assert result == 'HELLO'

    result = g.command.parse('COPY')
    assert result == 'COPY'

    result = g.command.parse('Delete')
    assert result == 'Delete'

    result = g.command.parse('print')
    assert result == 'print'


def test_fail_expression():
    g = Grammar(r'''
        start = "a" | "b" | Fail("must be 'a' or 'b'")
    ''')
    try:
        g.parse('c')
        assert False
    except Exception as exc:
        assert "must be 'a' or 'b'" in str(exc)
        assert "'a' | 'b'" in str(exc)


def test_binary_strings_and_regexes():
    g = Grammar(r'start = b"magic:" >> (b/[0-9A-F]{2}/ // b".")')
    assert g.parse(b'magic:01.23.AB') == [b'01', b'23', b'AB']

    g = Grammar(r'start = b"\x01\x02\x03" >> (b/[\x00-\x0F]{2}/ // b"\xFF")')
    result = g.parse(b'\x01\x02\x03\x0F\x0F\xFF\x0E\x0E\xFF\x0D\x0D')
    assert result == [b'\x0F\x0F', b'\x0E\x0E', b'\x0D\x0D']


def test_repeat_operator_with_fixed_length():
    g = Grammar(r'''
        start = (Digit{3})+
        Digit = /\d/ |> `int`
    ''')
    assert g.parse('123456') == [[1, 2, 3], [4, 5, 6]]

    # Now try reading the count from the input.
    g = Grammar(r'''
        start = (let count = Number in Number{count})+
        Number = /\d+/ |> `int`
        ignore /\s+/
    ''')

    assert g.parse(' 3 10 20 30 ') == [[10, 20, 30]]

    try:
        assert g.parse(' 3 10 20 30 2 40 50 ') == [[10, 20, 30], [40, 50]]
    except g.PartialParseError as exc:
        print(exc.partial_result)


def test_repeat_operator_with_min_length():
    g = Grammar(r'''
        start = NumberSequence // ":"
        NumberSequence = Digit{2,}
        Digit = /\d/ |> `int`
    ''')

    assert g.parse('123:45:6789') == [[1, 2, 3], [4, 5], [6, 7, 8, 9]]

    with pytest.raises(g.PartialParseError):
        g.parse('123:45:6')


def test_repeat_operator_with_max_length():
    g = Grammar(r'''
        start = NumberSequence // ":"
        NumberSequence = Digit{,3}
        Digit = /\d/ |> `int`
    ''')

    assert g.parse('123:45:6') == [[1, 2, 3], [4, 5], [6]]

    with pytest.raises(g.PartialParseError):
        assert g.parse('123:45:6789')


def test_repeat_operator_with_min_and_max_length():
    g = Grammar(r'''
        start = NumberSequence // ":"
        NumberSequence = Digit{2,3}
        Digit = /\d/ |> `int`
    ''')

    assert g.parse('123:45:678') == [[1, 2, 3], [4, 5], [6, 7, 8]]

    with pytest.raises(g.PartialParseError):
        assert g.parse('123:45:6789')

    with pytest.raises(g.PartialParseError):
        assert g.parse('123:45:6')


def test_length_prefix_on_number_list_in_byte_string():
    g = Grammar(r'''
        Section =>
            let size = Length in
            Byte{size} |> `lambda x: b''.join(x)`

        Length = Byte |> `ord`
        Byte = b/./
    ''')
    assert g.parse(b'\x03abc') == b'abc'
