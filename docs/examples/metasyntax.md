# Metasyntax

This example shows how Sourcer parses grammar definitions. (It's a definition of
Sourcer's grammar, using Sourcer's grammar, if that makes any sense.)

<!-- skip example -->
~~~
```
import textwrap
```

ignored Space = /[ \t]+/
ignored Comment = /#[^\r\n]*/

Newline = /[\r\n][\s]*/
LineSep = Some(Newline | ";")
Name = /[_a-zA-Z][_a-zA-Z0-9]*/
QualifiedName = (Name // ".") |> `lambda x: '.'.join(x)`

Comma = wrap(",")

wrap(x) => Skip(Newline) >> x << Skip(Newline)

# Parse a full word, then see if it matches our keyword. The point is to make
# sure that we don't simply match the first part of a word. (For example, if
# the input string is "classify", we wouldn't want to match the keyword "class".)
kw(word) => Name where `lambda x: x == word`

Params = wrap("(") >> (wrap(Name) /? Comma) << ")"
IgnoreKeyword = kw("ignored") | kw("ignore")
OverrideKeyword = kw("overrides") | kw("override")

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
    is_override: Opt(OverrideKeyword) |> `bool`
    is_ignored: Opt(IgnoreKeyword) |> `bool`
    name: Name
    params: Opt(Params) << wrap("=>" | "=" | ":")
    expr: Expr
}

class ClassDef {
    name: kw("class") >> Name
    params: Opt(Params)
    members: wrap("{") >> (ClassMember /? LineSep) << "}"
}

class ClassMember {
    is_omitted: Opt("let") |> `bool`
    name: Name << wrap("=>" | "=" | ":")
    expr: Expr
}

class IgnoreStmt {
    expr: IgnoreKeyword >> Expr
}

class GrammarDef {
    head: Opt(GrammarHead << Skip(Newline))
    body: ManyStmts | SingleExpr
}

class GrammarHead {
    name: kw("grammar") >> QualifiedName
    extends: Opt(kw("extends") >> QualifiedName)
}

Stmt = ClassDef
    | RuleDef
    | IgnoreStmt
    | PythonSection
    | PythonExpression

class LetExpression {
    name: kw("let") >> Name << wrap("=>" | "=" | ":")
    expr: Expr << wrap(kw("in"))
    body: Expr
}

class Ref {
    value: Name
}

class ListLiteral {
    elements: "[" >> (wrap(Expr) /? Comma) << "]"
}

class ByteLiteral {
    prefix: /0[xX]/
    value: /[0-9a-fA-F]{2}/ |> `lambda x: int(x, 16)`
}

Atom = StringLiteral
    | RegexLiteral
    | LetExpression
    | ListLiteral
    | ByteLiteral
    | PythonExpression
    | Ref

class KeywordArg {
    name: Name << ("=>" | "=" | ":")
    expr: Expr
}

class ArgList {
    args: "(" >> (wrap(KeywordArg | Expr) /? Comma) << ")"
}

Expr = Atom between {
    mixfix: "(" >> wrap(Expr) << ")"
    postfix: ArgList, FieldAccess
    postfix: "?", "*", "+", Repeat
    left: wrap("//" | "/?")
    left: wrap("<<" | ">>")
    left: wrap("<|" | "|>" | "where")
    left: wrap("|")
    postfix: OperatorTable
}

class FieldAccess {
    field: "." >> Name
}

class Repeat {
    open: "{"
    start: RepeatArg?
    stop: ("," >> RepeatArg) | ("," >> None) | `start`
    close: "}"
}

RepeatArg = PythonExpression | Ref

class OperatorTable {
    rows: wrap(kw("between"))
        >> "{"
        >> Skip(Newline)
        >> Sep(OperatorRow, LineSep, allow_trailer=True, allow_empty=True)
        << "}"
}

class OperatorRow {
    associativity: Associativity
    operators: ":" >> (Expr // ",")
}

Associativity = kw("left")
    | kw("right")
    | kw("infix")
    | kw("mixfix")
    | kw("postfix")
    | kw("prefix")

ManyStmts = Sep(Stmt, LineSep, allow_trailer=True, allow_empty=False)
SingleExpr = Expr << Opt(LineSep)
start = Skip(Newline) >> GrammarDef
~~~

As part of Sourcer's build process, it reads
[this definition](https://github.com/jvs/sourcer/blob/master/grammar.txt)
and then generates a
[Python parser for it](https://github.com/jvs/sourcer/blob/master/sourcer/parser.py).
