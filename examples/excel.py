from sourcer import Grammar


description = r'''
    `from ast import literal_eval`

    start = Formula
    Formula = "="? >> Expr # << End

    ignored Space = @/[ \t\n\r]+/

    Offset = @/\d+|\[\-?\d+\]/

    class R1C1Ref {
        row = "R" >> Offset
        col = "C" >> Offset
    }

    class A1Ref {
        col_modifier = "$"?
        col = @/I[A-V]|[A-H][A-Z]|[A-Z]/
        row_modifier = "$"?
        row = @/\d+/
    }

    class DateTime {
        string = @/\d{4}-\d\d-\d\d \d\d:\d\d:\d\d/
    }

    Word = @/[a-zA-Z_\@][a-zA-Z0-9_\.\@]*/

    LongNumber = @/[0-9]\.[0-9]+(e|E)(\+|\-)[0-9]+/ |> `literal_eval`
    ShortNumber = @/[0-9]+(\.[0-9]*)?|\.[0-9]+/ |> `literal_eval`

    String = @/"([^"]|"")*"/ |> `lambda x: x[1:-1].replace('""', '"')`
    Sheet = @/'([^']|'')*'/ |> `lambda x: x[1:-1].repalce("''", "'")`

    Error = @/\#[a-zA-Z0-9_\/]+(\!|\?)?/ |> `lambda x: {'error': x}`

    Array = "{" >> (ExprList / ";") << "}"

    class FunctionCall {
        name = Word
        arguments = "(" >> ExprList << ")"
    }

    class CellRef {
        book = Opt("[" >> (Word | String) << "]")
        sheet = Opt((R1C1Ref | A1Ref | Word | Sheet) << "!")
        cell = R1C1Ref | A1Ref
    }

    Atom = "(" >> Expr << ")"
        | Array
        | FunctionCall
        | CellRef
        | Word
        | ShortNumber
        | LongNumber
        | String
        | DateTime
        | Error

    Operators(allow_union) => OperatorPrecedence(
        Atom,
        LeftAssoc(":"),
        LeftAssoc(""),
        LeftAssoc("," where `lambda _: allow_union`),
        Prefix("-" | "+"),
        Postfix("%"),
        RightAssoc("^"),
        LeftAssoc("*" | "/"),
        LeftAssoc("+" | "-"),
        LeftAssoc("&"),
        LeftAssoc("=" | "!=" | "<>" | "<=" | ">=" | "<" | ">"),
    )

    Expr = Operators(allow_union=`True`)
    ExprList = Operators(allow_union=`False`)? / ","
'''

grammar = Grammar(description, include_source=True)
