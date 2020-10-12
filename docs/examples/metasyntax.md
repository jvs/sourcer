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
    left: "{" >> Expr
    right: Opt("," >> Expr) << "}"
}

start = Skip(Newline) >> (Stmt /? Sep)
~~~

As part of Sourcer's build process, it reads
[this definition](https://github.com/jvs/sourcer/blob/master/metasyntax.txt)
and then generates a
[Python parser for it](https://github.com/jvs/sourcer/blob/master/sourcer/meta.py).


### Isn't this a chicken and egg problem?

Yeah, totally!

This isn't important to know, but if you ever run into a similar problem, here's
how Sourcer tackled it: Early on, now buried somewhere in Sourcer's git history,
Sourcer defined its metasyntax using its internal Python classes.

So for example, take `start = Skip(Newline) >> (Stmt /? Sep)`. Using Sourcer's
internal classes, that would be
`start = Discard(Skip(Newline), Alt(Stmt, Sep, allow_trailer=True))`.

Because the grammar rules are recursive, it also needed a way for rules to
express "forward references" -- references to rules that would be defined later
on in the Python code. So this isn't quite the whole story, but that's
the gist of it: Source defined its grammar using its expression classes.

(One quick note about recursion: This is why Sourcer needs a grammar, and not
just a bunch of regexes. In some ways, you can think of Sourcer as just an engine
for recursive regular expressions.)
