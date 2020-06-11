import unittest
from examples.excel import grammar as g


# Test cases from:
# http://www.ewbi.com/ewbi.develop/samples/jsport_nonEAT.html
ewbi_cases = [
    '=1+3+5',
    '=3 * 4 + 5',
    '=50',
    '=1+1',
    '=$A1',
    '=$B$2',
    '=SUM(B5:B15)',
    '=SUM(B5:B15,D5:D15)',
    '=SUM(B5:B15 A7:D7)',
    '=SUM(sheet1!$A$1:$B$2)',
    '=[data.xls]sheet1!$A$1',
    '=SUM((A:A 1:1))',
    '=SUM((A:A,1:1))',
    '=SUM((A:A A1:B1))',
    '=SUM(D9:D11,E9:E11,F9:F11)',
    '=SUM((D9:D11,(E9:E11,F9:F11)))',
    '=IF(P5=1.0,"NA",IF(P5=2.0,"A",IF(P5=3.0,"B",IF(P5=4.0,"C",IF(P'
        '5=5.0,"D",IF(P5=6.0,"E",IF(P5=7.0,"F",IF(P5=8.0,"G")))))))'
        ')',
    '={SUM(B2:D2*B3:D3)}',
    '=SUM(123 + SUM(456) + (45<6))+456+789',
    '=AVG(((((123 + 4 + AVG(A1:A2))))))',
    '=IF("a"={"a","b";"c",#N/A;-1,TRUE}, "yes", "no") &   "  more "'
        '"test"" text"',
    '=+ AName- (-+-+-2^6) = {"A","B"} + @SUM(R1C1) + (@ERROR.TYPE(#'
        'VALUE!) = 2)',
    '=IF(R13C3>DATE(2002,1,6),0,IF(ISERROR(R[41]C[2]),0,IF(R13C3>=R'
        '[41]C[2],0, IF(AND(R[23]C[11]>=55,R[24]C[11]>=20),R53C3,0)'
        ')))',
    '=IF(R[39]C[11]>65,R[25]C[42],ROUND((R[11]C[11]*IF(OR(AND(R[39]'
        'C[11]>=55, R[40]C[11]>=20),AND(R[40]C[11]>=20,R11C3="YES")'
        '),R[44]C[11],R[43]C[11]))+(R[14]C[11] *IF(OR(AND(R[39]C[11'
        ']>=55,R[40]C[11]>=20),AND(R[40]C[11]>=20,R11C3="YES")), R['
        '45]C[11],R[43]C[11])),0))',
]


class TestExcelFormulas(unittest.TestCase):
    def test_A1_notation_1(self):
        result = g.parse('AB20')
        self.assertEqual(result, g.CellRef(
            book=None,
            sheet=None,
            cell=g.A1Ref(
                col_modifier=None,
                col='AB',
                row_modifier=None,
                row='20',
            ),
        ))

    def test_A1_notation_2(self):
        result = g.parse('$C12')
        self.assertEqual(result, g.CellRef(
            book=None,
            sheet=None,
            cell=g.A1Ref(
                col_modifier=g.ShortSymbol('$'),
                col='C',
                row_modifier=None,
                row='12',
            ),
        ))

    def test_A1_notation_3(self):
        result = g.parse('Q$4')
        self.assertEqual(result, g.CellRef(
            book=None,
            sheet=None,
            cell=g.A1Ref(
                col_modifier=None,
                col='Q',
                row_modifier=g.ShortSymbol('$'),
                row='4',
            ),
        ))

    def test_A1_notation_4(self):
        result = g.parse('$HZ$100')
        self.assertEqual(result, g.CellRef(
            book=None,
            sheet=None,
            cell=g.A1Ref(
                col_modifier=g.ShortSymbol('$'),
                col='HZ',
                row_modifier=g.ShortSymbol('$'),
                row='100',
            ),
        ))

    def test_R1C1_notation_1(self):
        result = g.parse('R1C1')
        self.assertEqual(result, g.CellRef(
            book=None,
            sheet=None,
            cell=g.R1C1Ref(row='1', col='1'),
        ))

    def _test_R1C1_notation_2(self):
        result = g.parse('=R[-1]C1')
        self.assertEqual(result, g.CellRef(
            book=None,
            sheet=None,
            cell=g.R1C1Ref(row='[-1]', col='1'),
        ))

    def test_R1C1_notation_3(self):
        result = g.parse('=R[3]C[5]')
        self.assertEqual(result, g.CellRef(
            book=None,
            sheet=None,
            cell=g.R1C1Ref(row='[3]', col='[5]'),
        ))

    def test_R1C1_notation_4(self):
        result = g.parse('R99C[-10]')
        self.assertEqual(result, g.CellRef(
            book=None,
            sheet=None,
            cell=g.R1C1Ref(row='99', col='[-10]'),
        ))

    def test_cell_reference_with_sheet(self):
        result = g.parse('=sheet1!Z$9')
        self.assertEqual(result, g.CellRef(
            book=None,
            sheet=g.Word('sheet1'),
            cell=g.A1Ref(
                col_modifier=None,
                col='Z',
                row_modifier=g.ShortSymbol('$'),
                row='9',
            ),
        ))

    def test_full_cell_reference_1(self):
        result = g.parse('=[data.xls]sheet1!$AA$11')
        self.assertEqual(result, g.CellRef(
            book='data.xls',
            sheet=g.Word('sheet1'),
            cell=g.A1Ref(
                col_modifier=g.ShortSymbol('$'),
                col='AA',
                row_modifier=g.ShortSymbol('$'),
                row='11',
            ),
        ))

    def test_full_cell_reference_2(self):
        result = g.parse('=["foo ""bar"" [baz].xls"]D2!E9')
        self.assertEqual(result, g.CellRef(
            book=g.String('"foo ""bar"" [baz].xls"'),
            sheet=g.A1Ref(col_modifier=None, col='D', row_modifier=None, row='2'),
            cell=g.A1Ref(col_modifier=None, col='E', row_modifier=None, row='9'),
        ))

    def test_func_call_with_simple_range(self):
        result = g.parse('=SUM(B5:B15)')
        self.assertEqual(result,  g.FunctionCall(
            name=g.Word('SUM', pos=1),
            arguments=[
                g.InfixOp(
                    left=g.CellRef(
                        book=None,
                        sheet=None,
                        cell=g.A1Ref(
                            col_modifier=None, col='B',
                            row_modifier=None, row='5',
                        ),
                    ),
                    operator=g.ShortSymbol(':', pos=7),
                    right=g.CellRef(
                        book=None,
                        sheet=None,
                        cell=g.A1Ref(
                            col_modifier=None, col='B',
                            row_modifier=None, row='15',
                        ),
                    ),
                ),
            ],
        ))

    def test_coarse_grained_failures(self):
        # For now, simply make sure that we don't raise an exception
        # when parsing any of the formauls.
        assert all(g.parse(i) for i in ewbi_cases)


if __name__ == '__main__':
    unittest.main()
