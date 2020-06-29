import importlib
import subprocess

import sourcer


description = r'''
    ```
    import ast
    import textwrap
    ```

    ignored Space = @/[ \t]+/
    ignored Comment = @/#[^\r\n]*/

    Newline = @/[\r\n][\s]*/
    Sep = Some(Newline | ";")
    Name = @/[_a-zA-Z][_a-zA-Z0-9]*/
    Comma = wrap(",")

    template wrap(x) => Skip(Newline) >> x << Skip(Newline)

    # TODO: Make sure we don't match the first part of a longer word.
    template kw(x) => x

    class StringLiteral {
        value: (
            @/(?s)("""([^\\]|\\.)*?""")/
            | @/(?s)('\''([^\\]|\\.)*?'\'')/
            | @/("([^"\\]|\\.)*")/
            | @/('([^'\\]|\\.)*')/
        ) |> `ast.literal_eval`
    }

    class RegexLiteral {
        # Remove the leading "@/" and the trailing "/".
        value: @/\@\/([^\/\\]|\\.)*\// |> `lambda x: x[2:-1]`
    }

    class PythonSection {
        # Strip the backticks and remove any common indentation.
        value: @/(?s)```.*?```/ |> `lambda x: textwrap.dedent(x[3:-3])`
    }

    class PythonExpression {
        # Strip the backticks.
        value: @/`.*?`/ |> `lambda x: x[1:-1]`
    }

    class RuleDef {
        is_ignored: kw("ignored" | "ignore")?
        name: Name << ("=" | ":")
        expr: Expr
    }

    class ClassDef {
        name: kw("class") >> Name
        fields: wrap("{") >> (RuleDef / Sep) << "}"
    }

    class TemplateDef {
        name: kw("template") >> Name
        params: wrap("(") >> (wrap(Name) / Comma) << ")"
        expr: wrap("=>" | "=" | ":") >> Expr
    }

    Stmt = ClassDef
        | TemplateDef
        | RuleDef
        | PythonSection
        | PythonExpression

    class Ref {
        value: Name
    }

    class ListLiteral {
        elements: "[" >> (wrap(Expr) / Comma) << "]"
    }

    Atom = ("(" >> wrap(Expr) << ")")
        | Ref
        | StringLiteral
        | RegexLiteral
        | ListLiteral
        | PythonExpression

    class KeywordArg {
        name: Name << ("=" | ":")
        expr: Expr
    }

    class ArgList {
        args: "(" >> (wrap(KeywordArg | Expr) / Comma) << ")"
    }

    Expr = OperatorPrecedence(
        Atom,
        Postfix(ArgList),
        Postfix("?" | "*" | "+" | "!"),
        LeftAssoc(wrap("//" | "/")),
        LeftAssoc(wrap("<<" | ">>")),
        LeftAssoc(wrap("<|" | "|>")),
        LeftAssoc(wrap("|")),
    )

    # TODO: Implement `End`.
    start = Skip(Newline) >> (Stmt / Sep) # << End
'''


def run(description):
    grammar = sourcer.Grammar(description, include_source=True)

    # Make sure that the grammar describes itself.
    assert grammar.parse(description)

    # Save our current code for meta.py.
    with open('sourcer/meta.py', 'r') as f:
        was = f.read()

    # Replace it with our new code.
    with open('sourcer/meta.py', 'w') as f:
        f.write(f'# Generated by ../{__file__}\n')
        f.write(grammar._source_code)

    # Reload sourcer to load the new code.
    importlib.reload(sourcer)

    # Try parsing the description again, this time using the new code. Then try
    # running the tests.
    try:
        new_grammar = sourcer.Grammar(description, include_source=True)
        assert new_grammar.parse(description)
        subprocess.run('python -m pytest tests', shell=True, check=True)
    except Exception:
        # If we failed, restore the old code and re-raise the exception.
        with open('sourcer/meta.py', 'w') as f:
            f.write(was)
        raise


if __name__ == '__main__':
    run(description)
