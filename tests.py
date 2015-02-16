import unittest

import collections
import operator
import re

import peg
from peg import *


Int = Transform(Regex(r'\d+'), int)
Name = Regex(r'\w+')
Number = peg.TokenClass('Number', r'\d+')
Negation = collections.namedtuple('Negation', 'operator, right')


class TestSimpleExpressions(unittest.TestCase):
    def test_single_token_success(self):
        ans = parse(Number, '123')
        self.assertIsInstance(ans, Token)
        self.assertIsInstance(ans, Number)
        self.assertEqual(ans.content, '123')

    def test_single_token_failure(self):
        with self.assertRaises(ParseError):
            parse(Number, '123X')

    def test_prefix_token_success(self):
        ans = parse_prefix(Number, '123ABC')
        self.assertIsInstance(ans, ParseResult)
        token, pos = ans
        self.assertIsInstance(token, Token)
        self.assertIsInstance(token, Number)
        self.assertEqual(token.content, '123')
        self.assertEqual(pos, 3)

    def test_prefix_token_failure(self):
        with self.assertRaises(ParseError):
            parse_prefix(Number, 'ABC')

    def test_simple_transform(self):
        ans = parse(Int, '123')
        self.assertEqual(ans, 123)

    def test_left_assoc(self):
        Add = ReduceLeft(Int, '+', Int)
        ans = parse(Add, '1+2+3+4')
        self.assertEqual(ans, (((1, '+', 2), '+', 3), '+', 4))

    def test_right_assoc(self):
        Arrow = ReduceRight(Int, '->', Int)
        ans = parse(Arrow, '1->2->3->4')
        self.assertEqual(ans, (1, '->', (2, '->', (3, '->', 4))))

    def test_simple_struct(self):
        class Pair(Struct):
            def __init__(self):
                self.left = Int
                self.sep = ','
                self.right = Int

        ans = parse(Pair, '10,20')
        self.assertIsInstance(ans, Pair)
        self.assertEqual(ans.left, 10)
        self.assertEqual(ans.sep, ',')
        self.assertEqual(ans.right, 20)

    def test_two_simple_structs(self):
        class NumberPair(Struct):
            def __init__(self):
                self.left = Int
                self.sep = ','
                self.right = Int

        class LetterPair(Struct):
            def __init__(self):
                self.left = 'A'
                self.sep = ','
                self.right = 'B'

        Pair = NumberPair | LetterPair
        TwoPairs = (Pair, ',', Pair)
        ans1, comma, ans2 = parse(TwoPairs, 'A,B,100,200')
        self.assertIsInstance(ans1, LetterPair)
        self.assertEqual((ans1.left, ans1.right), ('A', 'B'))
        self.assertEqual(comma, ',')
        self.assertIsInstance(ans2, NumberPair)
        self.assertEqual((ans2.left, ans2.right), (100, 200))

    def test_simple_alt_sequence(self):
        Nums = Alt(Int, ',')
        ans = parse(Nums, '1,2,3,4')
        self.assertEqual(ans, [1,2,3,4])

    def test_opt_term_present(self):
        Seq = ('A', Opt('B'))
        ans = parse(Seq, 'AB')
        self.assertEqual(ans, ('A', 'B'))

    def test_opt_term_missing_front(self):
        Seq = (Opt('A'), 'B')
        ans = parse(Seq, 'B')
        self.assertEqual(ans, (None, 'B'))

    def test_opt_term_missing_middle(self):
        Seq = ('A', Opt('B'), 'C')
        ans = parse(Seq, 'AC')
        self.assertEqual(ans, ('A', None, 'C'))

    def test_opt_term_missing_end(self):
        Seq = ('A', Opt('B'))
        ans = parse(Seq, 'A')
        self.assertEqual(ans, ('A', None))

    def test_left_term(self):
        T = Left('A', 'B')
        ans = parse(T, 'AB')
        self.assertEqual(ans, 'A')

    def test_right_term(self):
        T = Right('A', 'B')
        ans = parse(T, 'AB')
        self.assertEqual(ans, 'B')

    def test_require_success(self):
        T = Require(List('A'), lambda ans: len(ans) > 2)
        ans = parse(T, 'AAA')
        self.assertEqual(ans, list('AAA'))

    def test_require_failure(self):
        T = Require(List('A'), lambda ans: len(ans) > 2)
        with self.assertRaises(ParseError):
            ans = parse(T, 'AA')

    def test_ordered_choice_first(self):
        T = (Or('A', 'AB'), 'B')
        ans = parse(T, 'AB')
        self.assertEqual(ans, ('A', 'B'))

    def test_ordered_choice_second(self):
        T = Or('A', 'B')
        ans = parse(T, 'B')
        self.assertEqual(ans, 'B')

    def test_ordered_choice_third(self):
        T = Or(*'ABC')
        ans = parse(T, 'C')
        self.assertEqual(ans, 'C')

    def test_and_operator(self):
        T = And('ABC', 'A')
        ans = parse(T, 'ABC')
        self.assertEqual(ans, 'ABC')

    def test_expect_term(self):
        T = (Expect('A'), 'A')
        ans = parse(T, 'A')
        self.assertEqual(ans, ('A', 'A'))

    def test_empty_alt_term(self):
        T = Middle('(', Alt('A', ','), ')')
        ans = parse(T, '()')
        self.assertEqual(ans, [])

    def test_left_assoc_struct(self):
        class Dot(LeftAssoc):
            def __init__(self):
                self.left = Name
                self.op = '.'
                self.right = Name
            def __str__(self):
                return '(%s).%s' % (self.left, self.right)
        ans = parse(Dot, 'foo.bar.baz.qux')
        self.assertIsInstance(ans, Dot)
        self.assertEqual(ans.right, 'qux')
        self.assertEqual(ans.left.right, 'baz')
        self.assertEqual(ans.left.left.right, 'bar')
        self.assertEqual(ans.left.left.left, 'foo')
        self.assertEqual(str(ans), '(((foo).bar).baz).qux')

    def test_right_assoc_struct(self):
        class Arrow(RightAssoc):
            def __init__(self):
                self.left = Name
                self.op = ' -> '
                self.right = Name
            def __str__(self):
                return '%s -> (%s)' % (self.left, self.right)
        ans = parse(Arrow, 'a -> b -> c -> d')
        self.assertIsInstance(ans, Arrow)
        self.assertEqual(ans.left, 'a')
        self.assertEqual(ans.right.left, 'b')
        self.assertEqual(ans.right.right.left, 'c')
        self.assertEqual(ans.right.right.right, 'd')
        self.assertEqual(str(ans), 'a -> (b -> (c -> (d)))')

    def test_simple_where_term(self):
        vowels = 'aeiou'
        Vowel = Where(lambda x: x in vowels)
        Consonant = Where(lambda x: x not in vowels)
        Pattern = (Consonant, Vowel, Consonant)
        ans = parse(Pattern, 'bar')
        self.assertEqual(ans, tuple('bar'))
        with self.assertRaises(ParseError):
            parse(Pattern, 'foo')

    def test_list_of_numbers_as_source(self):
        Odd = Literal(1) | Literal(3)
        Even = Literal(2) | Literal(4)
        Pair = (Odd, Even)
        Pairs = List(Pair)
        ans = parse(Pairs, [1, 2, 3, 4, 3, 2])
        self.assertEqual(ans, [(1, 2), (3, 4), (3, 2)])

    def test_mixed_list_of_values_as_source(self):
        Null = Literal(None)
        Str = AnyInst(basestring)
        Int = AnyInst(int)
        Empty = Literal([])
        Intro = Literal([0, 0, 0])
        Body = (Intro, Empty, Int, Str, Null)
        source = [[0, 0, 0], [], 15, "ok bye", None]
        ans = parse(Body, source)
        self.assertEqual(ans, tuple(source))
        bad_source = [[0, 0, 1]] + source[1:]
        with self.assertRaises(ParseError):
            parse(Body, bad_source)

    def test_any_inst_with_multiple_classes(self):
        Str = AnyInst(basestring)
        Num = AnyInst(int, float)
        Nums = (Num, Num, Str)
        source = [0.0, 10, 'ok']
        ans = parse(Nums, source)
        self.assertEqual(ans, tuple(source))
        with self.assertRaises(ParseError):
            parse(Nums, [200, 'ok', 100])


class TestArithmeticExpressions(unittest.TestCase):
    def grammar(self):
        F = ForwardRef(lambda: Factor)
        E = ForwardRef(lambda: Expr)
        Parens = Middle('(', E, ')')
        Negate = Transform(('-', F), lambda p: Negation(*p))
        Factor = Int | Parens | Negate
        Term = ReduceLeft(Factor, Or('*', '/'), Factor) | Factor
        Expr = ReduceLeft(Term, Or('+', '-'), Term) | Term
        return Expr

    def parse(self, source):
        return parse(self.grammar(), source)

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
        F = ForwardRef(lambda: Factor)
        E = ForwardRef(lambda: Expr)
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
            return ReduceLeft(left, op, right, evaluate)
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
            ans = parse(grammar, expression)
            self.assertEqual(ans, eval(expression))


class TestEagerLambdaCalculus(unittest.TestCase):
    def grammar(self):
        Parens = Middle('(', ForwardRef(lambda: Expr), ')')

        class Identifier(Struct):
            def __init__(self):
                self.name = Name

            def __repr__(self):
                return self.name

            def evaluate(self, env):
                return env.get(self.name, self.name)

        class Abstraction(Struct):
            def __init__(self):
                self.symbol = '\\'
                self.parameter = Name
                self.separator = '.'
                self.space = Opt(' ')
                self.body = Expr

            def __repr__(self):
                return '(\\%s. %r)' % (self.parameter, self.body)

            def evaluate(self, env):
                def callback(arg):
                    child = env.copy()
                    child[self.parameter] = arg
                    return self.body.evaluate(child)
                return callback

        class Application(LeftAssoc):
            def __init__(self):
                self.left = Operand
                self.operator = ' '
                self.right = Operand

            def __repr__(self):
                return '%r %r' % (self.left, self.right)

            def evaluate(self, env):
                left = self.left.evaluate(env)
                right = self.right.evaluate(env)
                return left(right)

        Operand = Parens | Abstraction | Identifier
        Expr = Application | Operand
        return Expr

    def test_expressions(self):
        grammar = self.grammar()
        testcases = [
            ('x', 'x'),
            ('(x)', 'x'),
            (r'(\x. x) y', 'y'),
            (r'(\x. \y. x) a b', 'a'),
            (r'(\x. \y. y) a b', 'b'),
            (r'(\x. \y. x y) (\x. z) b', 'z'),
            (r'(\x. \y. y x) z (\x. x)', 'z'),
            (r'(\x. \y. \t. t x y) a b (\x. \y. x)', 'a'),
            (r'(\x. \y. \t. t x y) a b (\x. \y. y)', 'b'),
        ]
        for (test, expectation) in testcases:
            ast = parse(grammar, test)
            ans = ast.evaluate({})
            self.assertEqual(ans, expectation)


class TestTokenizer(unittest.TestCase):
    def tokenize(self, tokenizer, source):
        tokens = tokenizer.run(source)
        return [t.content for t in tokens]

    def test_numbers_and_spaces(self):
        T = Tokenizer()
        T.Word = r'\w+'
        T.Space = r'\s+'
        ans = self.tokenize(T, 'A B C')
        self.assertEqual(ans, list('A B C'))

    def test_numbers_and_spaces_with_regexes(self):
        T = Tokenizer()
        T.Word = Regex(r'\w+')
        T.Space = re.compile(r'\s+')
        ans = self.tokenize(T, 'A B C')
        self.assertEqual(ans, list('A B C'))

    def test_skip_spaces(self):
        T = Tokenizer()
        T.Number = r'\d+'
        T.Space = Skip(r'\s+')
        ans = self.tokenize(T, '1 2 3')
        self.assertEqual(ans, list('123'))

    def test_token_types(self):
        T = Tokenizer()
        T.Number = r'\d+'
        T.Space = Skip(r'\s+')
        tokens = T.run('1 2 3')
        self.assertIsInstance(tokens, list)
        self.assertEqual(len(tokens), 3)
        for index, token in enumerate(tokens):
            self.assertIsInstance(token, T.Number)
            self.assertEqual(token.content, str(index + 1))

    def test_one_char_in_string(self):
        T = Tokenizer()
        T.Symbol = AnyChar('(.*[;,])?')
        sample = '[]().*;;'
        ans = self.tokenize(T, sample)
        self.assertEqual(ans, list(sample))

    def test_init_style(self):
        class FooTokens(Tokenizer):
            def __init__(self):
                self.Space = Skip(r'\s+')
                self.Word = r'[a-zA-Z_][a-zA-Z_0-9]*'
                self.Symbol = Skip(AnyChar(',.;'))
        sample = 'This is a test, everybody.'
        ans = self.tokenize(FooTokens(), sample)
        self.assertEqual(ans, ['This', 'is', 'a', 'test', 'everybody'])

    def test_tokenize_and_parse(self):
        class CalcTokens(Tokenizer):
            def __init__(self):
                self.Space = Skip(r'\s+')
                self.Number = r'\d+'
                self.Operator = AnyChar('+*-/')
        class Factor(LeftAssoc):
            def __init__(self):
                self.left = Operand
                self.operator = Or('/', '*')
                self.right = Operand
        class Term(LeftAssoc):
            def __init__(self):
                self.left = Factor | Operand
                self.operator = Or('+', '-')
                self.right = Factor | Operand
        T = CalcTokens()
        Operand = T.Number
        sample = '1 + 2 * 3 - 4'
        ans = tokenize_and_parse(T, Term, sample)
        self.assertIsInstance(ans, Term)


class RegressionTests(unittest.TestCase):
    def test_stack_depth(self):
        test = ('(1+' * 100) + '1' + (')' * 100)
        Parens = Middle('(', ForwardRef(lambda: Add), ')')
        Term = Parens | '1'
        Add = (Term, '+', Term) | Term
        ans = parse(Add, test)
        self.assertIsInstance(ans, tuple)
        self.assertEqual(ans[0], '1')
        self.assertEqual(ans[1], '+')


if __name__ == '__main__':
    unittest.main()
