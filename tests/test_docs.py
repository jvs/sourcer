import glob
import exemplary

from sourcer import Grammar


def test_docs():
    pathnames = glob.glob('**/*.md', recursive=True)
    exemplary.run(pathnames, render=False)


def test_intitial_example():
    g = Grammar(r'''
        class Greeting {
            salutation: "Hello" | "Hi"i
            audience: Punctuation* >> Word << Punctuation*
        }

        Word = /[a-z]+/i
        Punctuation = "." | "!" | "?" | ","

        ignore /\s+/
        start = Greeting
    ''')

    result = g.parse('Hello, World!')
    assert result == g.Greeting(salutation='Hello', audience='World')

    result = g.parse('Hello?? Anybody?!')
    assert result == g.Greeting(salutation='Hello', audience='Anybody')

    result = g.parse('hi all')
    assert result == g.Greeting(salutation='hi', audience='all')
