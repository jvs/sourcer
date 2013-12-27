import unittest

import collections
import operator
import re

from peg import *


Int = Transform(re.compile(r'\d+'), int)
Number = Token(r'\d+')
Negation = collections.namedtuple('Negation', 'operator, right')


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
        self.assertEqual(ans, (((1, '+', 2), '+', 3), '+', 4))

    def test_right_assoc(self):
        Arrow = RightAssoc(Int, '->', Int)
        ans = parse_all(Arrow, '1->2->3->4')
        self.assertEqual(ans, (1, '->', (2, '->', (3, '->', 4))))

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

    def test_ordered_choice_first(self):
        T = (Or('A', 'AB'), 'B')
        ans = parse_all(T, 'AB')
        self.assertEqual(ans, ('A', 'B'))

    def test_ordered_choice_second(self):
        T = Or('A', 'B')
        ans = parse_all(T, 'B')
        self.assertEqual(ans, 'B')

    def test_ordered_choice_third(self):
        T = Or(*'ABC')
        ans = parse_all(T, 'C')
        self.assertEqual(ans, 'C')

    def test_and_operator(self):
        T = And('ABC', 'A')
        ans = parse_all(T, 'ABC')
        self.assertEqual(ans, 'ABC')

    def test_expect_term(self):
        T = (Expect('A'), 'A')
        ans = parse_all(T, 'A')
        self.assertEqual(ans, ('A', 'A'))


class TestArithmeticExpressions(unittest.TestCase):
    def grammar(self):
        F = Lazy(lambda: Factor)
        E = Lazy(lambda: Expr)
        Parens = Middle('(', E, ')')
        Negate = Transform(('-', F), lambda p: Negation(*p))
        Factor = Int | Parens | Negate
        Term = LeftAssoc(Factor, Or('*', '/'), Factor) | Factor
        Expr = LeftAssoc(Term, Or('+', '-'), Term) | Term
        return Expr

    def parse(self, source):
        return parse_all(self.grammar(), source)

    def test_ints(self):
        for i in range(10):
            ans = self.parse(str(i))
            self.assertEqual(ans, i)

    def test_int_in_parens(self):
        ans = self.parse('(100)')
        self.assertEqual(ans, 100)

    def test_many_parens(self):
        for i in range(10):
            prefix = '(' * i
            suffix = ')' * i
            ans = self.parse('%s%s%s' % (prefix, i, suffix))
            self.assertEqual(ans, i)

    def test_simple_negation(self):
        ans = self.parse('-50')
        self.assertEqual(ans, Negation('-', 50))

    def test_double_negation(self):
        ans = self.parse('--100')
        self.assertEqual(ans, Negation('-', Negation('-', 100)))

    def test_subtract_negative(self):
        ans = self.parse('1--2')
        self.assertEqual(ans, (1, '-', Negation('-', 2)))

    def test_simple_precedence(self):
        ans = self.parse('1+2*3')
        self.assertEqual(ans, (1, '+', (2, '*', 3)))

    def test_simple_precedence_with_parens(self):
        ans = self.parse('(1+2)*3')
        self.assertEqual(ans, ((1, '+', 2), '*', 3))

    def test_compound_term(self):
        t1 = self.parse('1+2*-3/4-5')
        t2 = self.parse('(1+((2*(-3))/4))-5')
        self.assertEqual(t1, t2)


class TestCalculator(unittest.TestCase):
    def grammar(self):
        F = Lazy(lambda: Factor)
        E = Lazy(lambda: Expr)
        Parens = Middle('(', E, ')')
        Negate = Transform(Right('-', F), lambda x: -x)
        Factor = Int | Parens | Negate
        operators = {
            '+': operator.add,
            '-': operator.sub,
            '*': operator.mul,
            '/': operator.div,
        }
        def evaluate(left, op, right):
            return operators[op](left, right)
        def binop(left, op, right):
            return LeftAssoc(left, op, right, evaluate)
        Term = binop(Factor, Or('*', '/'), Factor) | Factor
        Expr = binop(Term, Or('+', '-'), Term) | Term
        return Expr

    def test_expressions(self):
        grammar = self.grammar()
        expressions = [
            '1',
            '1+2',
            '1+2*3',
            '--1---2----3',
            '1+1+1+1',
            '1+2+3+4*5*6',
            '1+2+3*4-(5+6)/7',
            '(((1)))+(2)',
            '8/4/2',
        ]
        for expression in expressions:
            ans = parse_all(grammar, expression)
            self.assertEqual(ans, eval(expression))


if __name__ == '__main__':
    unittest.main()
