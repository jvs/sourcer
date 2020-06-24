from ast import literal_eval
import sourcer.expressions as sr
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

    Comma = wrap(",")

    class RuleDef {
        name: Name << ("=" | ":")
        expr: Expr
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
        params: wrap("(") >> (wrap(Name) / Comma) << ")"
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
        elements: "[" >> (wrap(Expr) / Comma) << "]"
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
        args: "(" >> (wrap(KeywordArg | Expr) / Comma) << ")"
    }

    Expr = OperatorPrecedence(
        Atom,
        Postfix(ArgList),
        Postfix("?" | "*" | "+" | "!"),
        LeftAssoc(wrap("/" | "//")),
        LeftAssoc(wrap("<<" | ">>" | "<<!" | "!>>")),
        LeftAssoc(wrap("|")),
    )

    start = Skip(Newline) >> (Def / Sep) << End
''')


result = g.parse(g.grammar)


def convert_tokens(node):
    if isinstance(node, (g.Symbol, g.Word)):
        return node.value

    if isinstance(node, g.StringLiteral):
        return sr.Literal(literal_eval(node.value))

    if isinstance(node, g.RegexLiteral):
        # Strip the backticks.
        return sr.Regex(node.value[1:-1])

    if isinstance(node, g.Ref):
        return sr.Ref(node.name)

    if isinstance(node, g.ListLiteral):
        return sr.Seq(*node.elements)

    if isinstance(node, g.PostfixOp) and isinstance(node.operator, g.ArgList):
        left = node.left
        classes = {
            'LeftAssoc': sr.LeftAssoc,
            'OperatorPrecedence': sr.OperatorPrecedence,
            'Postfix': sr.Postfix,
            'Skip': sr.Skip,
        }
        if isinstance(left, sr.Ref) and left.name in classes:
            return classes[left.name](*node.operator.args)
        elif isinstance(left, sr.Ref):
            return sr.Call(left.name, node.operator.args)

        raise NotImplementedError('Currently, function-calls only work for names.')

    if isinstance(node, g.PostfixOp):
        classes = {
            '?': sr.Opt,
            '*': sr.List,
            '+': sr.Some,
            # '!': sr.Commit,
        }
        if isinstance(node.operator, str) and node.operator in classes:
            return classes[node.operator](node.left)

    if isinstance(node, g.InfixOp) and node.operator == '|':
        left, right = node.left, node.right
        left = list(left.exprs) if isinstance(left, sr.Choice) else [left]
        right = list(right.exprs) if isinstance(right, sr.Choice) else [right]
        return sr.Choice(*left, *right)

    if isinstance(node, g.InfixOp):
        classes = {
            '/': lambda a, b: sr.Alt(a, b, allow_trailer=True),
            '//': lambda a, b: sr.Alt(a, b, allow_trailer=False),
            '<<': sr.Left,
            '>>': sr.Right,
            # '<<!': lambda a, b: sr.Left(a, sr.Commit(b)),
            # '!>>': lambda a, b: sr.Left(sr.Commit(a), b),
        }
        return classes[node.operator](node.left, node.right)

    if isinstance(node, g.RuleDef):
        return sr.Rule(node.name, node.expr)

    return node


converted = g.transform(result, convert_tokens)
for item in converted:
    print('\n')
    print(item)
