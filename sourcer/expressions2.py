from collections import namedtuple
from functools import reduce
import re
import types
import typing


def parse(expr, text, pos=0):
    expr = conv(expr)
    stack = [expr._parse(text, pos)]
    result = None
    while stack:
        top = stack[-1]
        result = top.send(result)
        if isinstance(result, Step):
            stack.append(result.expr._parse(text, result.pos))
            result = None
        else:
            stack.pop()
    assert result is not None
    if result.is_success:
        return result.value
    else:
        raise ParseError(result.error_message())


class ParseError(Exception):
    """Indicates that the `parse` function failed."""


class Parser:
    def __init__(self, start, tokens=None, transform_tokens=None):
        self.start = conv(start)
        self._tokenizer = Tokenizer(*tokens) if tokens else None
        self.transform_tokens = transform_tokens

    def __call__(self, text):
        return self.parse(text)

    def parse(self, text):
        if isinstance(text, str) and self._tokenizer:
            text = self._tokenize(text)
        return parse(self.start, text)

    def tokenize(self, text):
        if self._tokenizer:
            return self._tokenize(text)
        else:
            raise ParseError('Parser does not have any token definitions.')

    def _tokenize(self, text):
        tokens = parse(self._tokenizer, text)
        return self.transform_tokens(tokens) if self.transform_tokens else tokens


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

    def _parse(self, text, pos):
        delegate = self.derive()
        self._parse = delegate._parse
        return delegate._parse(text, pos)


class Alt(Expr):
    def __init__(self, expr, separator, allow_trailer=False):
        self.expr = conv(expr)
        self.separator = conv(separator)
        self.allow_trailer = allow_trailer

    def _parse(self, text, pos):
        result = []
        result_pos = pos
        saw_commit = False
        while True:
            item = yield Step(self.expr, pos)
            if not item.is_success:
                break
            if not saw_commit and item.is_commit:
                saw_commit = True
            result.append(item.value)
            pos = item.pos
            result_pos = pos
            skipped = yield Step(self.separator, pos)
            if not skipped.is_success:
                break
            if not saw_commit and skipped.is_commit:
                saw_commit = True
            pos = skipped.pos
            if self.allow_trailer:
                result_pos = pos
        yield Success(result, result_pos, is_commit=saw_commit)


class Any(metaclass=MetaExpr):
    @classmethod
    def _parse(cls, text, pos):
        yield Success(text[pos], pos + 1) if pos < len(text) else Failure(cls, pos)


class Choice(Expr):
    def __init__(self, *exprs):
        # Flatten any nested Choice expressions.
        self.exprs = []
        for x in exprs:
            x = conv(x)
            if isinstance(x, Choice):
                self.exprs.extend(x.exprs)
            else:
                self.exprs.append(x)

    def _parse(self, text, pos):
        best_failure = None
        for expr in self.exprs:
            result = yield Step(expr, pos)

            # Consume the "is_commit" flag.
            if result.is_success:
                if result.is_commit:
                    yield Success(result.value, result.pos, is_commit=False)
                else:
                    yield result
                return

            # Consume the "is_abort" flag.
            if result.is_abort:
                yield Failure(result.expr, result.pos, is_abort=False)
                return

            # Keep track of the failure that consumed the most input.
            if best_failure is None or best_failure.pos < result.pos:
                best_failure = result

        yield best_failure if best_failure is not None else Failure(self, pos)


class Commit(Expr):
    def __init__(self, expr):
        self.expr = conv(expr)

    def _parse(self, text, pos):
        result = yield Step(self.expr, pos)
        yield result.commit() if result.is_success else result


class Expect(Expr):
    def __init__(self, expr):
        self.expr = conv(expr)

    def _parse(self, text, pos):
        result = yield Step(self.expr, pos)
        yield result.backtrack(pos) if result.is_success else result


class ExpectNot(Expr):
    def __init__(self, expr):
        self.expr = conv(expr)

    def _parse(self, text, pos):
        result = yield Step(self.expr, pos)
        yield Failure(self, pos) if result.is_success else Success(None, pos)


class Fail(Expr):
    def __init__(self, message):
        self.message = message

    def _parse(self, text, pos):
        yield Failure(self, pos)


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

    def _parse(self, text, pos):
        result = []
        saw_commit = False
        while True:
            item = yield Step(self.expr, pos)
            if not item.is_success:
                break
            pos = item.pos
            value = item.value
            if isinstance(value, Token) and value.is_dropped:
                continue
            result.append(value)
            if not saw_commit and item.is_commit:
                saw_commit = True
        yield Success(result, pos, is_commit=saw_commit)


class Literal(Expr):
    def __init__(self, value):
        self.value = value
        self._delegate = Require(Any, lambda x: x == self.value)

    def _parse(self, text, pos):
        if isinstance(text, str):
            return self._parse_str(text, pos)
        else:
            return self._delegate._parse(text, pos)

    def _parse_str(self, text, pos):
        if not isinstance(self.value, str):
            yield Failure(self, pos)
            return

        end = pos + len(self.value)
        if end <= len(text) and self.value == text[pos:end]:
            yield Success(self.value, end)
        else:
            yield Failure(self, pos)


class Opt(DerivedExpr):
    def __init__(self, expr):
        self.expr = conv(expr)

    def derive(self):
        return Choice(self.expr, Pass(None))


class Pass(Expr):
    def __init__(self, value):
        self.value = value

    def _parse(self, text, pos):
        yield Success(self.value, pos)


class Regex(Expr):
    def __init__(self, pattern):
        if isinstance(pattern, str):
            pattern = re.compile(pattern)
        elif not isinstance(pattern, typing.Pattern):
            raise TypeError('Expected Pattern object')
        self.pattern = pattern

    def _parse(self, text, pos):
        if isinstance(text, str):
            m = self.pattern.match(text, pos)
            yield Success(m.group(0), m.end()) if m else Failure(self, pos)
            return

        if pos >= len(text):
            yield Failure(self, pos)
            return

        item = text[pos]
        value = item.value if isinstance(item, Token) else item
        match = self.pattern.fullmatch(value) if isinstance(value, str) else None
        yield Success(item, pos + 1) if match else Failure(self, pos)


class Require(Expr):
    def __init__(self, expr, pred=bool):
        self.expr = conv(expr)
        self.pred = pred

    def _parse(self, text, pos):
        result = yield Step(self.expr, pos)
        if not result.is_success or self.pred(result.value):
            yield result
        else:
            yield Failure(self, pos)


class Right(DerivedExpr):
    def __init__(self, expr1, expr2):
        self.expr1 = conv(expr1)
        self.expr2 = conv(expr2)

    def derive(self):
        return Transform(Seq(self.expr1, self.expr2), lambda x: x[1])


class Seq(Expr):
    def __init__(self, *exprs):
        self.exprs = [conv(x) for x in exprs]

    def _parse(self, text, pos):
        result = []
        saw_commit = False
        for expr in self.exprs:
            item = yield Step(expr, pos)
            if not item.is_success:
                yield item.abort() if saw_commit else item
                return
            if not saw_commit and item.is_commit:
                saw_commit = True
            result.append(item.value)
            pos = item.pos
        yield Success(result, pos, is_commit=saw_commit)


class Skip(Expr):
    def __init__(self, expr):
        self.expr = conv(expr)

    def _parse(self, text, pos):
        while True:
            item = yield Step(self.expr, pos)
            if item.is_success:
                pos = item.pos
            else:
                break
        yield Success(None, pos)


class Some(DerivedExpr):
    def __init__(self, expr):
        self.expr = conv(expr)

    def derive(self):
        return Require(List(self.expr))


class Struct(metaclass=MetaExpr):
    def __init__(self, **kw):
        if not hasattr(self, '_fields'):
            self.__class__._parse('', 0)

        if set(kw.keys()) != set(self._fields):
            raise Exception(f'Expected fields: {self._fields!r}')

        for k, v in kw.items():
            setattr(self, k, v)

    @classmethod
    def _parse(cls, text, pos):
        names, exprs = [], []
        for name, value in vars(cls).items():
            if not name.startswith('_') and not callable(value):
                names.append(name)
                exprs.append(conv(value))

        cls._fields = tuple(names)
        delegate = Choice(
            Transform(Seq(*exprs), lambda vals: cls(**dict(zip(names, vals)))),
            Require(Any, lambda x: isinstance(x, cls)),
        )
        cls._parse = delegate._parse
        return delegate._parse(text, pos)

    def _asdict(self):
        return {k: getattr(self, k) for k in self._fields}

    def _replace(self, **kw):
        if not kw:
            return self
        for field in self._fields:
            if field not in kw:
                kw[field] = getattr(self, field)
        return self.__class__(**kw)

    def __eq__(self, other):
        return (isinstance(other, self.__class__) and
            all(getattr(self, x) == getattr(other, x) for x in self._fields))

    def __repr__(self):
        name = self.__class__.__name__
        fields = ', '.join(f'{x}={getattr(self, x)!r}' for x in self._fields)
        return f'{name}({fields})'


class Token(metaclass=MetaExpr):
    def __init__(self, value, pos=None):
        self.value = value
        self.pos = pos

    @classmethod
    def _parse(cls, text, pos):
        if isinstance(text, str):
            return cls._parse_str(text, pos)
        else:
            return cls._parse_item(text, pos)

    @classmethod
    def _parse_str(cls, text, pos):
        result = yield Step(cls.pattern, pos)
        if isinstance(result, Success):
            token = cls(result.value, pos)
            yield Success(token, result.pos)
        else:
            yield result

    @classmethod
    def _parse_item(cls, text, pos):
        delegate = Require(Any, lambda x: isinstance(x, cls))
        cls._parse_item = delegate._parse
        return delegate._parse(text, pos)

    def __eq__(self, other):
        if isinstance(other, str):
            return self.value == other
        else:
            return isinstance(other, Token) and self.value == other.value


def TokenClass(pattern, is_dropped=False):
    class TokenClass(Token):
        def __repr__(self):
            name = self.__class__.__name__
            if name == 'TokenClass':
                name = 'Token'
            return f'{name}({self.value!r})'
    TokenClass.pattern = conv(pattern)
    TokenClass.is_dropped = is_dropped
    return TokenClass


def TokenPattern(pattern, is_dropped=False):
    return TokenClass(Regex(pattern), is_dropped=is_dropped)


def Tokenizer(*exprs):
    return List(Choice(*exprs)) << End


class Transform(Expr):
    def __init__(self, expr, func):
        self.expr = expr
        self.func = func

    def _parse(self, text, pos):
        result = yield Step(self.expr, pos)
        if isinstance(result, Success):
            value = self.func(result.value)
            yield Success(value, result.pos)
        else:
            yield result


InfixOp = namedtuple('Infix', 'left, operator, right')
PrefixOp = namedtuple('PrefixOp', 'operator, right')
PostfixOp = namedtuple('PostfixOp', 'left, operator')


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


class Postfix(OperatorPrecedenceRule):
    def build(self, operand):
        expr = Seq(operand, List(self.operators))
        return Transform(expr, lambda seq: reduce(PostfixOp, seq[1], seq[0]))


class Prefix(OperatorPrecedenceRule):
    def build(self, operand):
        expr = Seq(List(self.operators), operand)
        make_op = lambda acc, op: PrefixOp(op, acc)
        return Transform(expr, lambda seq: reduce(make_op, reversed(seq[0]), seq[1]))


def OperatorPrecedence(atom, *rules):
    return reduce(lambda acc, rule: rule.build(acc), rules, atom)


def visit(tree):
    if isinstance(tree, (InfixOp, Postfix, PrefixOp, Token, Struct)):
        yield tree

    if isinstance(tree, (list, InfixOp, Postfix, PrefixOp)):
        for item in tree:
            yield from visit(item)

    if isinstance(tree, Struct):
        for field in tree._fields:
            yield from visit(getattr(tree, field))


def transform(tree, callback):
    if isinstance(tree, list):
        return [transform(x, callback) for x in tree]

    if isinstance(tree, Token):
        return callback(tree)

    if not isinstance(tree, (InfixOp, PostfixOp, PrefixOp, Struct)):
        return tree

    has_changes = False
    updates = {}
    for field in tree._fields:
        was = getattr(tree, field)
        now = transform(was, callback)
        updates[field] = now
        if not has_changes and was is not now:
            has_changes = True

    if has_changes:
        tree = tree._replace(**updates)

    return callback(tree)


Step = namedtuple('Step', 'expr, pos')


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
