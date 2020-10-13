# Metasyntax

This example shows how Sourcer parses grammar definitions. (It's a definition of
Sourcer's grammar, using Sourcer's grammar, if that makes any sense.)

~~~
```
import textwrap
```

ignored Space = /[ \t]+/
ignored Comment = /#[^\r\n]*/

Newline = /[\r\n][\s]*/
Sep = Some(Newline | ";")
Name = /[_a-zA-Z][_a-zA-Z0-9]*/
Comma = wrap(",")

wrap(x) => Skip(Newline) >> x << Skip(Newline)

# Parse a full word, then see if it matches our keyword. The point is to make
# sure that we don't simply match the first part of a word. (For example, if
# the input string is "classify", we wouldn't want to match the keyword "class".)
kw(word) => Name where `lambda x: x == word`

Params = wrap("(") >> (wrap(Name) /? Comma) << ")"
IgnoreKeyword = kw("ignored") | kw("ignore")

class StringLiteral {
    value: (
        /(?s)[bB]?("""([^\\]|\\.)*?""")[iI]?/
        | /(?s)[bB]?('''([^\\]|\\.)*?''')[iI]?/
        | /[bB]?("([^"\\]|\\.)*")[iI]?/
        | /[bB]?('([^'\\]|\\.)*')[iI]?/
    )
}

class RegexLiteral {
    value: /[bB]?\/([^\/\\]|\\.)*\/[iI]?/
}

class PythonSection {
    # Strip the backticks and remove any common indentation.
    value: /(?s)```.*?```/ |> `lambda x: textwrap.dedent(x[3:-3])`
}

class PythonExpression {
    # Strip the backticks.
    value: /`.*?`/ |> `lambda x: x[1:-1]`
        | /\d+/
        | "True"
        | "False"
        | "None"
}

class RuleDef {
    is_ignored: Opt(IgnoreKeyword) |> `bool`
    name: Name
    params: Opt(Params) << wrap("=>" | "=" | ":")
    expr: Expr
}

class ClassDef {
    name: kw("class") >> Name
    params: Opt(Params)
    fields: wrap("{") >> (RuleDef /? Sep) << "}"
}

class IgnoreStmt {
    expr: IgnoreKeyword >> Expr
}

Stmt = ClassDef
    | RuleDef
    | IgnoreStmt
    | PythonSection
    | PythonExpression

class LetExpression {
    name: kw("let") >> Name << wrap("=")
    expr: Expr << wrap(kw("in"))
    body: Expr
}

class Ref {
    value: Name
}

class ListLiteral {
    elements: "[" >> (wrap(Expr) /? Comma) << "]"
}

Atom = ("(" >> wrap(Expr) << ")")
    | StringLiteral
    | RegexLiteral
    | LetExpression
    | ListLiteral
    | PythonExpression
    | Ref

class KeywordArg {
    name: Name << ("=" | ":")
    expr: Expr
}

class ArgList {
    args: "(" >> (wrap(KeywordArg | Expr) /? Comma) << ")"
}

Expr = OperatorPrecedence(
    Atom,
    Postfix(ArgList),
    Postfix("?" | "*" | "+" | Repeat),
    LeftAssoc(wrap("//" | "/?")),
    LeftAssoc(wrap("<<" | ">>")),
    LeftAssoc(wrap("<|" | "|>" | "where")),
    LeftAssoc(wrap("|")),
)

class Repeat {
    open: "{"
    start: RepeatArg?
    stop: ("," >> RepeatArg) | ("," >> None) | `start`
    close: "}"
}

RepeatArg = PythonExpression | Ref

start = Skip(Newline) >> (Stmt /? Sep)
~~~

As part of Sourcer's build process, it reads
[this definition](https://github.com/jvs/sourcer/blob/master/metasyntax.txt)
and then generates a
[Python parser for it](https://github.com/jvs/sourcer/blob/master/sourcer/meta.py).
