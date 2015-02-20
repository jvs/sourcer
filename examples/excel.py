from sourcer import *


def parse_formula(formula):
    return tokenize_and_parse(Tokens, Formula, formula)


class FormulaTokenizer(Tokenizer):
    def __init__(self):
        offset = lambda n: r'(?P<raw_%s>(\d+|\[\-?\d+\]))' % n
        self.R1C1Ref = 'R%sC%s' % (offset('row'), offset('column'))
        self.A1Ref = Verbose(r'''
            (?P<column_modifier>\$?)
            (?P<column>I[A-V]|[A-H][A-Z]|[A-Z])
            (?P<row_modifier>\$?)
            (?P<row>\d+)
        ''')
        self.Word = r'[a-zA-Z_\@][a-zA-Z0-9_\.\@]*'
        self.DateTime = r'\d{4}-\d\d-\d\d \d\d:\d\d:\d\d'
        self.Space = Skip(r'[ \t\n\r]+')
        self.LongNumber = r'[0-9]\.[0-9]+(e|E)(\+|\-)[0-9]+'
        self.ShortNumber = r'[0-9]+(\.[0-9]*)?|\.[0-9]+'
        self.LongSymbol = r'(\!\=)|(\<\>)|(\<\=)|(\>\=)'
        self.ShortSymbol = AnyChar(':$!+-*/<>=^%&,;[]{}()')
        self.String = r'"([^"]|"")*"'
        self.Sheet = r"'([^']|'')*'"
        self.Error = r'\#[a-zA-Z0-9_\/]+(\!|\?)?'


Tokens = FormulaTokenizer()
Name = Content(Tokens.Word)


class Array(Struct):
    def __init__(self):
        self.elements = Middle('{', ExprList / ';', '}')


class FunctionCall(Struct):
    def __init__(self):
        self.name = Name
        self.arguments = Middle('(', ExprList, ')')


def _normalize_R1C1(token):
    def visit(n):
        value = getattr(token, 'raw_' + n)
        is_sq = value.startswith('[')
        setattr(token, n, value[1:-1] if is_sq else value)
        setattr(token, n + '_modifier', '[]' if is_sq else '')
    visit('row')
    visit('column')
    return token


class CellRef(Struct):
    def __init__(self):
        strip = lambda c: lambda x: x.content[1:-1].replace(c + c, c)
        String = Transform(Tokens.String, strip('"'))
        Sheet = Transform(Tokens.Sheet, strip("'"))
        Cell = Tokens.A1Ref | Transform(Tokens.R1C1Ref, _normalize_R1C1)
        self.book = ~Middle('[', Name | String, ']')
        self.sheet = ~Left(Cell | Name | Sheet, '!')
        self.cell = Cell

    def __getattr__(self, name):
        return getattr(self.cell, name)


Atom = (
    Middle('(', ForwardRef(lambda: Expr), ')')
    | Array
    | FunctionCall
    | CellRef
    | Name
    | Tokens.ShortNumber
    | Tokens.LongNumber
    | Tokens.String
    | Tokens.DateTime
    | Tokens.Error
)


def build_precedence_table(allow_unions):
    return OperatorPrecedence(
        Atom,
        InfixLeft(':'),
        InfixLeft(None),
        InfixLeft(',') if allow_unions else Prefix(),
        Prefix('-', '+'),
        Postfix('%'),
        InfixRight('^'),
        InfixLeft('*', '/'),
        InfixLeft('+', '-'),
        InfixLeft('&'),
        InfixLeft('=', '!=', '<>', '<', '<=', '>', '>='),
    )


Expr = build_precedence_table(True)
ExprElmt = build_precedence_table(False)
ExprList = ~ExprElmt / ','
Formula = Right(Opt('='), Expr)
