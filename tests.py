import unittest

import re
from peg import *


Int = Transform(re.compile(r'\d+'), int)
Number = Token(r'\d+')


class TestSimpleExpressions(unittest.TestCase):
    def test_single_token_success(self):
        ans = parse_all(Number, '123')
        self.assertIsInstance(ans, BaseToken)
        self.assertIsInstance(ans, Number)
        self.assertEqual(ans.content, '123')

    def test_single_token_failure(self):
        with self.assertRaises(ParseError):
            parse_all(Number, '123X')

    def test_prefix_token_success(self):
        ans = parse(Number, '123ABC')
        self.assertIsInstance(ans, ParseResult)
        token, pos = ans
        self.assertIsInstance(token, BaseToken)
        self.assertIsInstance(token, Number)
        self.assertEqual(token.content, '123')
        self.assertEqual(pos, 3)

    def test_prefix_token_failure(self):
        with self.assertRaises(ParseError):
            parse(Number, 'ABC')

    def test_simple_transform(self):
        ans = parse_all(Int, '123')
        self.assertEqual(ans, 123)

    def test_left_assoc(self):
        Add = LeftAssoc(Int, '+', Int)
        ans = parse_all(Add, '1+2+3+4')
        A = lambda x, y: BinaryOperation(x, '+', y)
        self.assertEqual(ans, A(A(A(1, 2), 3), 4))

    def test_right_assoc(self):
        Arrow = RightAssoc(Int, '->', Int)
        ans = parse_all(Arrow, '1->2->3->4')
        A = lambda x, y: BinaryOperation(x, '->', y)
        self.assertEqual(ans, A(1, A(2, A(3, 4))))

    def test_simple_struct(self):
        class Pair(Struct):
            def __init__(self):
                self.left = Int
                self.sep = ','
                self.right = Int

        ans = parse_all(Pair, '10,20')
        self.assertIsInstance(ans, Pair)
        self.assertEqual(ans.left, 10)
        self.assertEqual(ans.sep, ',')
        self.assertEqual(ans.right, 20)

    def test_simple_alt_sequence(self):
        Nums = Alt(Int, ',')
        ans = parse_all(Nums, '1,2,3,4')
        self.assertEqual(ans, [1,2,3,4])

    def test_opt_term_present(self):
        Seq = ('A', Opt('B'))
        ans = parse_all(Seq, 'AB')
        self.assertEqual(ans, ('A', 'B'))

    def test_opt_term_missing_front(self):
        Seq = (Opt('A'), 'B')
        ans = parse_all(Seq, 'B')
        self.assertEqual(ans, (None, 'B'))

    def test_opt_term_missing_middle(self):
        Seq = ('A', Opt('B'), 'C')
        ans = parse_all(Seq, 'AC')
        self.assertEqual(ans, ('A', None, 'C'))

    def test_opt_term_missing_end(self):
        Seq = ('A', Opt('B'))
        ans = parse_all(Seq, 'A')
        self.assertEqual(ans, ('A', None))

    def test_left_term(self):
        T = Left('A', 'B')
        ans = parse_all(T, 'AB')
        self.assertEqual(ans, 'A')

    def test_right_term(self):
        T = Right('A', 'B')
        ans = parse_all(T, 'AB')
        self.assertEqual(ans, 'B')

    def test_require_success(self):
        T = Require(List('A'), lambda ans: len(ans) > 2)
        ans = parse_all(T, 'AAA')
        self.assertEqual(ans, list('AAA'))

    def test_require_failure(self):
        T = Require(List('A'), lambda ans: len(ans) > 2)
        with self.assertRaises(ParseError):
            ans = parse_all(T, 'AA')


if __name__ == '__main__':
    unittest.main()
