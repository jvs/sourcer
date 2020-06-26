from sourcer import Grammar


def test_simple_words():
    g = Grammar(r'''
        ignored token Space = `[ \t]+`
        token Word = `[_a-zA-Z][_a-zA-Z0-9]*`
        start = Word*
    ''')

    result = g.parse('foo bar baz')
    assert result == [g.Word('foo'), g.Word('bar'), g.Word('baz')]
