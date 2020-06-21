from ast import literal_eval
import sourcer.expressions
from .metasyntax import Grammar, transform_tokens


g = Grammar(r'''
    ignored token Space = `[ \t]+`
    token Word = `[_a-zA-Z][_a-zA-Z0-9]*`
    token Symbol = `<<\!|\!>>|<<|>>|=>|\/\/|[=;,:\|\/\*\+\?\!\(\)\[\]\{\}]`

    token StringLiteral = (
        `("([^"\\]|\\.)*")`
        | `('([^'\\]|\\.)*')`
        | `("""([^\\]|\\.)*?""")`
        | `('\''([^\\]|\\.)*?'\'')`
    )

    token RegexLiteral = `\`([^\`\\]|\\.)*\``
    token Newline = `[\r\n][\s]*`
    ignored token Comment = `#[^\r\n]*`

    Sep = Some(Newline | ";")
    Name = Word

    template wrap(x) => Skip(Newline) >> x << Skip(Newline)

    class RuleDef {
        name: Name << ("=" | ":")
        value: Expr
    }

    class ClassDef {
        name: "class" >> Name
        fields: wrap("{") >> (RuleDef / Sep) << "}"
    }

    class TokenDef {
        is_ignored: ("ignore" | "ignored")?
        child: "token" >> (ClassDef | RuleDef)
    }

    class TemplateDef {
        name: "template" >> Name
        params: wrap("(") >> (Name / ",") << ")"
        body: wrap("=" | ":" | "=>") >> Expr
    }

    Def = TokenDef
        | ClassDef
        | TemplateDef
        | RuleDef

    class Ref {
        name: Word
    }

    class ListLiteral {
        elements: "[" >> (Expr / ",") << "]"
    }

    Atom = ("(" >> wrap(Expr) << ")")
        | Ref
        | StringLiteral
        | RegexLiteral
        | ListLiteral

    class KeywordArg {
        name: Name << ("=" | ":")
        value: Expr
    }

    class ArgList {
        args: "(" >> (wrap(KeywordArg | Expr) / wrap(",")) << ")"
    }

    Expr = OperatorPrecedence(
        Atom,
        Postfix(ArgList),
        Postfix("?" | "*" | "+" | "!"),
        LeftAssoc(wrap("/" | "//")),
        LeftAssoc(wrap("<<" | ">>")),
        LeftAssoc(wrap("|")),
    )

    start = Skip(Newline) >> (Def / Sep) << End
''')


result = g.parse(g.grammar)


def convert_tokens(node):
    if isinstance(node, (g.Symbol, g.Word)):
        return node.value

    if isinstance(node, g.StringLiteral):
        return sourcer.expressions.Literal(literal_eval(node.value))

    if isinstance(node, g.RegexLiteral):
        # Strip the backticks.
        return sourcer.expressions.Regex(node.value[1:-1])

    if isinstance(node, g.Ref):
        return sourcer.expressions.Ref(node.name)

    return node


converted = g.transform(result, convert_tokens)
print(converted)
