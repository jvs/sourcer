from sourcer import Grammar


grammar = Grammar(r'''
    start = Formula
    Formula = "="? >> Expr # << End

    # TODO: Allow "Offset" to be defined outside the token definition.
    # Offset = `\d+|\[\-?\d+\]`

    token class R1C1Ref {
        row = "R" >> `\d+|\[\-?\d+\]`
        col = "C" >> `\d+|\[\-?\d+\]`
    }

    token class A1Ref {
        col_modifier = "$"?
        col = `I[A-V]|[A-H][A-Z]|[A-Z]`
        row_modifier = "$"?
        row = `\d+`
    }

    ignored token Space = `[ \t\n\r]+`

    token Word = `[a-zA-Z_\@][a-zA-Z0-9_\.\@]*`
    token DateTime = `\d{4}-\d\d-\d\d \d\d:\d\d:\d\d`
    token LongNumber = `[0-9]\.[0-9]+(e|E)(\+|\-)[0-9]+`
    token ShortNumber = `[0-9]+(\.[0-9]*)?|\.[0-9]+`
    token LongSymbol = `(\!\=)|(\<\>)|(\<\=)|(\>\=)`
    token ShortSymbol = `[:\$\!\+\-\*\/<>=\^%&,;\[\]\{\}\(\)]`
    token String = `"([^"]|"")*"`
    token Sheet = `'([^']|'')*'`
    token Error = `\#[a-zA-Z0-9_\/]+(\!|\?)?`

    class Array {
        elements = "{" >> (ExprList / ";") << "}"
    }

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

    template Operators(union_operator) => OperatorPrecedence(
        Atom,
        LeftAssoc(":"),
        LeftAssoc(""),
        union_operator,
        Prefix("-" | "+"),
        Postfix("%"),
        RightAssoc("^"),
        LeftAssoc("*" | "/"),
        LeftAssoc("+" | "-"),
        LeftAssoc("&"),
        LeftAssoc("=" | "!=" | "<>" | "<" | ">" | ">="),
    )

    Expr = Operators(LeftAssoc(","))
    ExprList = Operators(LeftAssoc(Fail("Expected list.")))? / ","
''', include_source=True)
