import unittest
from sourcer import Operation
from examples.excel import *


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
        ans = parse_formula('AB20')
        self.assertIsInstance(ans, CellRef)
        self.assertIsNone(ans.book)
        self.assertIsNone(ans.sheet)
        self.assertEqual(ans.column_modifier, '')
        self.assertEqual(ans.column, 'AB')
        self.assertEqual(ans.row_modifier, '')
        self.assertEqual(ans.row, '20')

    def test_A1_notation_2(self):
        ans = parse_formula('$C12')
        self.assertIsInstance(ans, CellRef)
        self.assertIsNone(ans.book)
        self.assertIsNone(ans.sheet)
        self.assertEqual(ans.column_modifier, '$')
        self.assertEqual(ans.column, 'C')
        self.assertEqual(ans.row_modifier, '')
        self.assertEqual(ans.row, '12')

    def test_A1_notation_3(self):
        ans = parse_formula('Q$4')
        self.assertIsInstance(ans, CellRef)
        self.assertIsNone(ans.book)
        self.assertIsNone(ans.sheet)
        self.assertEqual(ans.column_modifier, '')
        self.assertEqual(ans.column, 'Q')
        self.assertEqual(ans.row_modifier, '$')
        self.assertEqual(ans.row, '4')

    def test_A1_notation_4(self):
        ans = parse_formula('$HZ$100')
        self.assertIsInstance(ans, CellRef)
        self.assertIsNone(ans.book)
        self.assertIsNone(ans.sheet)
        self.assertEqual(ans.column_modifier, '$')
        self.assertEqual(ans.column, 'HZ')
        self.assertEqual(ans.row_modifier, '$')
        self.assertEqual(ans.row, '100')

    def test_R1C1_notation_1(self):
        ans = parse_formula('R1C1')
        self.assertIsInstance(ans, CellRef)
        self.assertIsNone(ans.book)
        self.assertIsNone(ans.sheet)
        self.assertEqual(ans.row_modifier, '')
        self.assertEqual(ans.row, '1')
        self.assertEqual(ans.column_modifier, '')
        self.assertEqual(ans.column, '1')

    def test_R1C1_notation_2(self):
        ans = parse_formula('=R[-1]C1')
        self.assertIsInstance(ans, CellRef)
        self.assertIsNone(ans.book)
        self.assertIsNone(ans.sheet)
        self.assertEqual(ans.row_modifier, '[]')
        self.assertEqual(ans.row, '-1')
        self.assertEqual(ans.column_modifier, '')
        self.assertEqual(ans.column, '1')

    def test_R1C1_notation_3(self):
        ans = parse_formula('=R[3]C[5]')
        self.assertIsInstance(ans, CellRef)
        self.assertIsNone(ans.book)
        self.assertIsNone(ans.sheet)
        self.assertEqual(ans.row_modifier, '[]')
        self.assertEqual(ans.row, '3')
        self.assertEqual(ans.column_modifier, '[]')
        self.assertEqual(ans.column, '5')

    def test_R1C1_notation_4(self):
        ans = parse_formula('R99C[-10]')
        self.assertIsInstance(ans, CellRef)
        self.assertIsNone(ans.book)
        self.assertIsNone(ans.sheet)
        self.assertEqual(ans.row_modifier, '')
        self.assertEqual(ans.row, '99')
        self.assertEqual(ans.column_modifier, '[]')
        self.assertEqual(ans.column, '-10')

    def test_cell_reference_with_sheet(self):
        ans = parse_formula('=sheet1!Z$9')
        self.assertIsInstance(ans, CellRef)
        self.assertIsNone(ans.book)
        self.assertEqual(ans.sheet, 'sheet1')
        self.assertEqual(ans.column_modifier, '')
        self.assertEqual(ans.column, 'Z')
        self.assertEqual(ans.row_modifier, '$')
        self.assertEqual(ans.row, '9')

    def test_full_cell_reference_1(self):
        ans = parse_formula('=[data.xls]sheet1!$AA$11')
        self.assertIsInstance(ans, CellRef)
        self.assertEqual(ans.book, 'data.xls')
        self.assertEqual(ans.sheet, 'sheet1')
        self.assertEqual(ans.column_modifier, '$')
        self.assertEqual(ans.column, 'AA')
        self.assertEqual(ans.row_modifier, '$')
        self.assertEqual(ans.row, '11')

    def test_full_cell_reference_2(self):
        ans = parse_formula('=["foo ""bar"" [baz].xls"]D2!E9')
        self.assertIsInstance(ans, CellRef)
        self.assertEqual(ans.book, 'foo "bar" [baz].xls')
        self.assertEqual(ans.sheet.column, 'D')
        self.assertEqual(ans.sheet.row, '2')
        self.assertEqual(ans.sheet.content, 'D2')
        self.assertEqual(ans.column_modifier, '')
        self.assertEqual(ans.column, 'E')
        self.assertEqual(ans.row_modifier, '')
        self.assertEqual(ans.row, '9')

    def test_func_call_with_simple_range(self):
        ans = parse_formula('=SUM(B5:B15)')
        self.assertIsInstance(ans, FunctionCall)
        self.assertEqual(ans.name, 'SUM')
        self.assertEqual(len(ans.arguments), 1)
        arg = ans.arguments[0]
        self.assertIsInstance(arg, Operation)
        self.assertEqual(arg.operator, ':')
        self.assertIsInstance(arg.left, CellRef)
        self.assertIsInstance(arg.right, CellRef)
        self.assertEqual(arg.left.column, 'B')
        self.assertEqual(arg.right.column, 'B')
        self.assertEqual(arg.left.row, '5')
        self.assertEqual(arg.right.row, '15')

    def test_coarse_grained_failures(self):
        # For now, simply make sure that we don't raise an exception
        # when parsing any of the formauls.
        assert all(parse_formula(i) for i in ewbi_cases)


if __name__ == '__main__':
    unittest.main()
