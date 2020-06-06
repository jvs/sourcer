from collections import namedtuple
from functools import reduce
import inspect
import re
import types
import typing


def parse(expr, text, pos=0):
    result = conv(expr).parse(text, pos)
    if result.is_success:
        return result.value
    else:
        raise ParseError(result.error_message())


class ParseError(Exception):
    """Indicates that the `parse` function failed."""


class Parser:
    def __init__(self, start, tokens=None):
        if isinstance(tokens, (list, tuple)):
            self.tokenizer = Tokenizer(*tokens)
        self.start = conv(start)

    def __call__(self, text):
        return self.parse(text)

    def parse(self, text):
        if isinstance(text, str) and hasattr(self, 'tokenizer'):
            text = self._tokenize(text)
        return parse(self.start, text)

    def tokenize(self, text):
        if hasattr(self, 'tokenizer'):
            return self._tokenize(text)
        else:
            raise ParseError('Grammar does not have any token definitions.')

    def _tokenize(self, text):
        return parse(self.tokenizer, text)


class Expr:
    """
    This mixin adds support for parsing operators::

        Operator  Verbose Form      Description
        ========  ================  ===================
        a | b     Or(a, b)          ordered choice
        a / b     Alt(a, b, True)   alternation
        a // b    Alt(a, b, False)  separated list
        ~a        Opt(a)            optional value
        a >> b    Right(a, b)       discard a
        a << b    Left(a, b)        discard b
        a ^ b     Require(a, b)     predicate
        a * b     Transform(a, b)   transform
        a ** b    Bind(a, b)        context sensitivity
        ========  ===============   ===================
    """
    def __invert__(self): return Opt(self)
    def __or__(self, other): return Choice(self, other)
    def __ror__(self, other): return Choice(other, self)
    def __lshift__(self, other): return Left(self, other)
    def __rlshift__(self, other): return Left(other, self)
    def __rshift__(self, other): return Right(self, other)
    def __rrshift__(self, other): return Right(other, self)
    def __truediv__(self, other): return Alt(self, other, allow_trailer=True)
    def __rtruediv__(self, other): return Alt(other, self, allow_trailer=True)
    def __floordiv__(self, other): return Alt(self, other, allow_trailer=False)
    def __rfloordiv__(self, other): return Alt(other, self, allow_trailer=False)
    def __mul__(self, func): return Transform(self, func)
    def __xor__(self, pred): return Require(self, pred)


class MetaExpr(type, Expr):
    """This metaclass allows classes to overload the parsing operators."""


class DerivedExpr(Expr):
    """A parsing expression that can be derived from other expressions."""

    def derive(self):
        raise NotImplementedError('derive')

    def parse(self, text, pos):
        delegate = self.derive()
        self.parse = delegate.parse
        return delegate.parse(text, pos)


class Alt(Expr):
    def __init__(self, expr, separator, allow_trailer=False):
        self.expr = conv(expr)
        self.separator = conv(separator)
        self.allow_trailer = allow_trailer

    def parse(self, text, pos):
        result = []
        result_pos = pos
        saw_commit = False
        while True:
            item = self.expr.parse(text, pos)
            if not item.is_success:
                break
            if not saw_commit and item.is_commit:
                saw_commit = True
            result.append(item.value)
            pos = item.pos
            result_pos = pos
            skipped = self.separator.parse(text, pos)
            if not skipped.is_success:
                break
            if not saw_commit and skipped.is_commit:
                saw_commit = True
            pos = skipped.pos
            if self.allow_trailer:
                result_pos = pos
        return Success(result, result_pos, is_commit=saw_commit)


class Any(metaclass=MetaExpr):
    @classmethod
    def parse(cls, text, pos):
        return Success(text[pos], pos + 1) if pos < len(text) else Failure(cls, pos)


class Choice(Expr):
    def __init__(self, *exprs):
        self.exprs = [conv(x) for x in exprs]

    def parse(self, text, pos):
        best_failure = None
        for expr in self.exprs:
            result = expr.parse(text, pos)

            # Consume the "is_commit" flag.
            if result.is_success:
                if result.is_commit:
                    return Success(result.value, result.pos, is_commit=False)
                else:
                    return result

            # Consume the "is_abort" flag.
            if result.is_abort:
                return Failure(result.expr, result.pos, is_abort=False)

            # Keep track of the failure that consumed the most input.
            if best_failure is None or best_failure.pos < result.pos:
                best_failure = result

        return best_failure if best_failure is not None else Failure(self, pos)


class Commit(Expr):
    def __init__(self, expr):
        self.expr = conv(expr)

    def parse(self, text, pos):
        result = parse(text, pos, self.expr)
        return result.commit() if result.is_success else result


class Expect(Expr):
    def __init__(self, expr):
        self.expr = conv(expr)

    def parse(self, text, pos):
        result = self.expr.parse(text, pos)
        return result.backtrack(pos) if result.is_success else result


class ExpectNot(Expr):
    def __init__(self, expr):
        self.expr = conv(expr)

    def parse(self, text, pos):
        result = self.expr.parse(text, pos)
        return Failure(self, pos) if result.is_success else Success(None, pos)


class Fail(Expr):
    def __init__(self, message):
        self.message = message

    def parse(self, text, pos):
        return Failure(self, pos)


class Lazy(DerivedExpr):
    def __init__(self, func):
        self.func = func

    def derive(self):
        return conv(self.func())


class Left(DerivedExpr):
    def __init__(self, expr1, expr2):
        self.expr1 = conv(expr1)
        self.expr2 = conv(expr2)

    def derive(self):
        return Transform(Seq(self.expr1, self.expr2), lambda x: x[0])


class List(Expr):
    def __init__(self, expr):
        self.expr = conv(expr)

    def parse(self, text, pos):
        result = []
        saw_commit = False
        while True:
            item = self.expr.parse(text, pos)
            if not item.is_success:
                break
            result.append(item.value)
            pos = item.pos
            if not saw_commit and item.is_commit:
                saw_commit = True
        return Success(result, pos, is_commit=saw_commit)


class Literal(Expr):
    def __init__(self, value):
        self.value = value
        self._delegate = Require(Any, lambda x: x == self.value)

    def parse(self, text, pos):
        if isinstance(text, str):
            return self._parse_str(text, pos)
        else:
            return self._delegate.parse(text, pos)

    def _parse_str(self, text, pos):
        if not isinstance(self.value, str):
            return Failure(self, pos)
        end = pos + len(self.value)
        if end <= len(text) and self.value == text[pos:end]:
            return Success(self.value, end)
        else:
            return Failure(self, pos)


class Opt(DerivedExpr):
    def __init__(self, expr):
        self.expr = conv(expr)

    def derive(self):
        return Choice(self.expr, Pass(None))


class Pass(Expr):
    def __init__(self, value):
        self.value = value

    def parse(self, text, pos):
        return Success(self.value, pos)


class Regex(Expr):
    def __init__(self, pattern):
        if isinstance(pattern, str):
            pattern = re.compile(pattern)
        elif not isinstance(pattern, typing.Pattern):
            raise TypeError('Expected Pattern object')
        self.pattern = pattern

    def parse(self, text, pos):
        if isinstance(text, str):
            m = self.pattern.match(text, pos)
            return Success(m.group(0), m.end()) if m else Failure(self, pos)

        if pos >= len(text):
            return Failure(self, pos)

        item = text[pos]
        value = item.value if isinstance(item, Token) else item
        match = self.pattern.fullmatch(value)
        return Success(item, pos + 1) if match else Failure(self, pos)


class Require(Expr):
    def __init__(self, expr, pred=bool):
        self.expr = conv(expr)
        self.pred = pred

    def parse(self, text, pos):
        result = self.expr.parse(text, pos)
        if not result.is_success or self.pred(result.value):
            return result
        else:
            return Failure(self, pos)


class Right(DerivedExpr):
    def __init__(self, expr1, expr2):
        self.expr1 = conv(expr1)
        self.expr2 = conv(expr2)

    def derive(self):
        return Transform(Seq(self.expr1, self.expr2), lambda x: x[1])


class Seq(Expr):
    def __init__(self, *exprs):
        self.exprs = [conv(x) for x in exprs]

    def parse(self, text, pos):
        result = []
        saw_commit = False
        for expr in self.exprs:
            item = expr.parse(text, pos)
            if not item.is_success:
                return item.abort() if saw_commit else item
            if not saw_commit and item.is_commit:
                saw_commit = True
            result.append(item.value)
            pos = item.pos
        return Success(result, pos, is_commit=saw_commit)


class Some(DerivedExpr):
    def __init__(self, expr):
        self.expr = conv(expr)

    def derive(self):
        return Require(List(self.expr))


class Struct(metaclass=MetaExpr):
    @classmethod
    def parse(cls, text, pos):
        names, exprs = [], []
        for name, value in vars(cls).items():
            if not inspect.ismethod(value):
                names.append(name)
                exprs.append(conv(value))

        names = tuple(names)

        def init(values):
            obj = cls()
            obj._fields = names
            for name, value in zip(names, values):
                setattr(obj, name, value)
            return obj

        delegate = Transform(Seq(*exprs), init)
        cls.parse = delegate.parse
        return delegate.parse(text, pos)

    def _asdict(self):
        return {k: getattr(self, k) for k in self._fields}


class Token(metaclass=MetaExpr):
    def __init__(self, value, pos=None):
        self.value = value
        self.pos = pos

    @classmethod
    def parse(cls, text, pos):
        if isinstance(text, str):
            return cls._parse_str(text, pos)
        else:
            return cls._parse_item(text, pos)

    @classmethod
    def _parse_str(cls, text, pos):
        result = cls.pattern.parse(text, pos)
        if isinstance(result, Success):
            token = cls(result.value, pos)
            return Success(token, result.pos)
        else:
            return result

    @classmethod
    def _parse_item(cls, text, pos):
        delegate = Require(Any, lambda x: isinstance(x, cls))
        cls._parse_item = delegate.parse
        return delegate.parse(text, pos)

    def __eq__(self, other):
        if isinstance(other, str):
            return self.value == other
        else:
            return isinstance(other, Token) and self.value == other.value


def TokenClass(pattern):
    class TokenClass(Token):
        def __repr__(self):
            return f'Token({self.value!r})'
    TokenClass.pattern = conv(pattern)
    return TokenClass


def Tokenizer(*exprs):
    return List(Choice(*exprs)) << End


class Transform(Expr):
    def __init__(self, expr, func):
        self.expr = expr
        self.func = func

    def parse(self, text, pos):
        result = self.expr.parse(text, pos)
        if isinstance(result, Success):
            value = self.func(result.value)
            return Success(value, result.pos)
        else:
            return result


InfixOp = namedtuple('Infix', 'left, operator, right')
PrefixOp = namedtuple('Prefix', 'operator, right')
PostfixOp = namedtuple('Prefix', 'left, operator')


class OperatorPrecedenceRule:
    def __init__(self, *operators):
        self.operators = conv(operators[0]) if len(operators) == 1 else Choice(*operators)


class LeftAssoc(OperatorPrecedenceRule):
    def build(self, operand):
        expr = Seq(operand, List(Seq(self.operators, operand)))
        make_op = lambda acc, op_right: InfixOp(acc, *op_right)
        return Transform(expr, lambda seq: reduce(make_op, seq[1], seq[0]))


class NonAssoc(OperatorPrecedenceRule):
    def build(self, operand):
        expr = Seq(operand, Opt(Seq(self.operators, operand)))
        def make_op(seq):
            left, op_right = seq
            return left if op_right is None else InfixOp(left, *op_right)
        return Transform(expr, make_op)


class RightAssoc(OperatorPrecedenceRule):
    def build(self, operand):
        # This avoids backtracking, unlike the more obvious formulation of
        # `Seq(List(operand, operator), operand)` (which will backtrack and
        # parse the final operand twice).
        expr = Seq(operand, List(Seq(self.operators, operand)))
        def associate(seq):
            first, rest = seq
            if len(rest) == 0:
                return first

            # Awkwardly fold-right by manually decrementing an index variable.
            # SHOULD: Find a nicer way to do this...
            acc = rest[-1][-1]
            i = len(rest) - 1
            while i >= 0:
                op = rest[i][0]
                left = first if i == 0 else rest[i - 1][1]
                acc = InfixOp(left, op, acc)
                i -= 1
            return acc
        return Transform(expr, associate)


def OperatorPrecedence(atom, *rules):
    return reduce(lambda acc, rule: rule.build(acc), rules, atom)


class Success:
    def __init__(self, value, pos, is_commit=False):
        self.value = value
        self.pos = pos
        self.is_commit = is_commit

    def backtrack(self, pos):
        return Success(self.value, pos, is_commit=self.is_commit)

    def commit(self):
        return self if self.is_commit else Success(self.value, self.pos, is_commit=True)

    @property
    def is_success(self):
        return True


class Failure:
    def __init__(self, expr, pos, is_abort=False):
        self.expr = expr
        self.pos = pos
        self.is_abort = is_abort

    def abort(self):
        return self if self.is_abort else Failure(self.expr, self.pos, is_abort=True)

    @property
    def is_success(self):
        return False

    def error_message(self):
        # TODO: Inspect the expr and try to compose a useful error message.
        return f'Parse error at index {self.pos}: {self.expr!r}'


def conv(obj):
    """Converts a Python object to a parsing expression."""
    if isinstance(obj, Expr):
        return obj

    if isinstance(obj, list) and len(obj) == 1:
        return List(obj)

    if isinstance(obj, (list, tuple)):
        return Seq(*obj)

    if isinstance(obj, types.LambdaType):
        if not hasattr(obj, '_parsing_expression'):
            obj._parsing_expression = Lazy(obj)
        return obj._parsing_expression

    if isinstance(obj, typing.Pattern):
        return Regex(obj)
    else:
        return Literal(obj)


# Some useful aliases.
End = ExpectNot(Any)
opt = Opt
req = Require
