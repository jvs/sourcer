from collections import namedtuple
from functools import reduce
import re
import types
import typing


def parse(expr, text, pos=0):
    expr = conv(expr)
    key = (pos, expr)
    ctx = ParsingContext()
    generator = expr._parse(ctx, text, pos)
    stack = [(key, generator)]
    memo = {}
    result = None
    while stack:
        key, generator = stack[-1]
        result = generator.send(result)

        if isinstance(result, Step):
            expr, pos = result.expr, result.pos
            key = (pos, expr)
            if key in memo:
                result = memo[key]
            else:
                generator = expr._parse(ctx, text, pos)
                stack.append((key, generator))
                result = None
            continue

        stack.pop()
        memo[key] = result

    assert result is not None
    if result.is_success:
        return result.value
    else:
        raise ParseError(result.error_message())


class ParsingContext:
    def __init__(self):
        self.checkpoints = []
        self.commits = []


class ParseError(Exception):
    """Indicates that the `parse` function failed."""


ErrorTree = namedtuple('ErrorTree', 'failure, replacement')


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

    def _parse(self, ctx, text, pos):
        delegate = self.derive()
        self._parse = delegate._parse
        return delegate._parse(ctx, text, pos)


class All(Expr):
    def __init__(self, aggregator, *exprs):
        self.aggregator = aggregator
        self.exprs = [conv(x) for x in exprs]

    def _parse(self, ctx, text, pos):
        result = None
        best_failure = Failure(self, pos)

        for expr in self.exprs:
            next_result = yield Step(expr, pos)
            if next_result.is_success:
                result, should_stop = self.aggregator(result, next_result)
                if should_stop:
                    yield result
                    return
            elif best_failure is None or best_failure.pos < next_result.pos:
                best_failure = next_result

        yield result if result else best_failure


class Alt(Expr):
    def __init__(self, expr, separator, allow_trailer=False):
        self.expr = conv(expr)
        self.separator = conv(separator)
        self.allow_trailer = allow_trailer

    def _parse(self, ctx, text, pos):
        result = []
        result_pos = pos
        while True:
            item = yield Step(self.expr, pos)
            if not item.is_success:
                break
            result.append(item.value)
            pos = item.pos
            result_pos = pos
            skipped = yield Step(self.separator, pos)
            if not skipped.is_success:
                break
            pos = skipped.pos
            if self.allow_trailer:
                result_pos = pos
        yield Success(result, result_pos)


class Any(metaclass=MetaExpr):
    @classmethod
    def _parse(cls, ctx, text, pos):
        yield Success(text[pos], pos + 1) if pos < len(text) else Failure(cls, pos)


class Checkpoint(Expr):
    def __init__(self, expr):
        self.expr = conv(expr)
        self._recoveries = []
        self._recovery = None

    def add_recovery(self, expr):
        self._recoveries.append(conv(expr))
        self._recovery = None

    def _parse(self, ctx, text, pos):
        ctx.checkpoints.append(self)
        ctx.commits.append(False)
        result = yield Step(self.expr, pos)
        saw_commit = ctx.commits.pop()

        if result.is_success or not saw_commit:
            yield result
            return

        if self._recovery is None:
            self._recovery = Shortest(*self._recovery)

        replacement = yield Step(self._recovery, pos)
        if replacement.is_success:
            tree = ErrorTree(result, replacement)
            yield Success(tree, replacement.pos)
        else:
            raise ParseError(result.error_message())


    def __repr__(self):
        return f'Checkpoint({self.expr!r})'


class Choice(DerivedExpr):
    def __init__(self, *exprs):
        # Flatten any nested Choice expressions.
        self.exprs = []
        for x in exprs:
            x = conv(x)
            if isinstance(x, Choice):
                self.exprs.extend(x.exprs)
            else:
                self.exprs.append(x)

    def derive(self):
        return All(lambda was, now: (now, True), *self.exprs)

    def __repr__(self):
        parts = ', '.join(repr(x) for x in self.exprs)
        return f'Choice({parts})'


class Commit(Expr):
    def __init__(self, expr):
        self.expr = conv(expr)

    def _parse(self, ctx, text, pos):
        result = yield Step(self.expr, pos)
        if result.is_success and ctx.commits:
            ctx.commits[-1] = True
        yield result

    def __repr__(self):
        return f'Commit({self.expr!r})'


class Expect(Expr):
    def __init__(self, expr):
        self.expr = conv(expr)

    def _parse(self, ctx, text, pos):
        result = yield Step(self.expr, pos)
        yield Success(result.value, pos) if result.is_success else result


class ExpectNot(Expr):
    def __init__(self, expr):
        self.expr = conv(expr)

    def _parse(self, ctx, text, pos):
        result = yield Step(self.expr, pos)
        yield Failure(self, pos) if result.is_success else Success(None, pos)


class Fail(Expr):
    def __init__(self, message):
        self.message = message

    def _parse(self, ctx, text, pos):
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

    def __repr__(self):
        return f'Left({self.expr1!r}, {self.expr2!r})'


class List(Expr):
    def __init__(self, expr):
        self.expr = conv(expr)

    def _parse(self, ctx, text, pos):
        result = []
        while True:
            item = yield Step(self.expr, pos)
            if not item.is_success:
                break
            pos = item.pos
            value = item.value
            if not isinstance(value, Token) or not value._is_ignored:
                result.append(value)
        yield Success(result, pos)


class Literal(Expr):
    def __init__(self, value):
        self.value = value
        self._delegate = Require(Any, lambda x: x == self.value)

    def _parse(self, ctx, text, pos):
        if isinstance(text, str):
            return self._parse_str(text, pos)
        else:
            return self._delegate._parse(ctx, text, pos)

    def _parse_str(self, text, pos):
        if not isinstance(self.value, str):
            yield Failure(self, pos)
            return

        end = pos + len(self.value)
        if end <= len(text) and self.value == text[pos:end]:
            yield Success(self.value, end)
        else:
            yield Failure(self, pos)

    def __repr__(self):
        return f'Literal({self.value!r})'


class Longest(DerivedExpr):
    def __init__(self, *exprs):
        self.exprs = [conv(x) for x in exprs]

    def derive(self):
        def aggregate(was, now):
            result = now if was is None or now.pos > was.pos else was
            return (result, False)
        return All(aggregate, *self.exprs)


class Opt(DerivedExpr):
    def __init__(self, expr):
        self.expr = conv(expr)

    def derive(self):
        return Choice(self.expr, Pass(None))


class Pass(Expr):
    def __init__(self, value):
        self.value = value

    def _parse(self, ctx, text, pos):
        yield Success(self.value, pos)


class Regex(Expr):
    def __init__(self, pattern):
        if isinstance(pattern, str):
            pattern = re.compile(pattern)
        elif not isinstance(pattern, typing.Pattern):
            raise TypeError('Expected Pattern object')
        self.pattern = pattern

    def _parse(self, ctx, text, pos):
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

    def _parse(self, ctx, text, pos):
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

    def __repr__(self):
        return f'Right({self.expr1!r}, {self.expr2!r})'


class Seq(Expr):
    def __init__(self, *exprs):
        self.exprs = [conv(x) for x in exprs]

    def _parse(self, ctx, text, pos):
        result = []
        for expr in self.exprs:
            item = yield Step(expr, pos)
            if not item.is_success:
                yield item
                return
            else:
                result.append(item.value)
                pos = item.pos
        yield Success(result, pos)


class Shortest(DerivedExpr):
    def __init__(self, *exprs):
        self.exprs = [conv(x) for x in exprs]

    def derive(self):
        def aggregate(was, now):
            result = now if was is None or now.pos < was.pos else was
            return (result, False)
        return All(aggregate, *self.exprs)


class Skip(Expr):
    def __init__(self, expr):
        self.expr = conv(expr)

    def _parse(self, ctx, text, pos):
        while True:
            item = yield Step(self.expr, pos)
            if item.is_success:
                pos = item.pos
            else:
                break
        yield Success(None, pos)


def SkipTo(expr):
    return Skip(ExpectNot(expr) >> Any)


class Some(DerivedExpr):
    def __init__(self, expr):
        self.expr = conv(expr)

    def derive(self):
        return Require(List(self.expr))


class Struct(metaclass=MetaExpr):
    def __init__(self, **kw):
        if not hasattr(self, '_fields'):
            self.__class__._init_fields()

        if set(kw.keys()) != set(self._fields):
            raise Exception(f'Expected fields: {self._fields!r}')

        for k, v in kw.items():
            setattr(self, k, v)

    @classmethod
    def _init_fields(cls):
        names, exprs = [], []
        for name, value in vars(cls).items():
            # Ignore definitions that start with an underscore, and ignore all
            # property objects.
            if name.startswith('_') or isinstance(value, property):
                continue

            # Ignore callable objects, unless they're also Expr objects.
            if callable(value) and not isinstance(value, Expr):
                continue

            names.append(name)
            exprs.append(conv(value))

        cls._fields = tuple(names)
        delegate = Choice(
            Transform(Seq(*exprs), lambda vals: cls(**dict(zip(names, vals)))),
            Require(Any, lambda x: isinstance(x, cls)),
        )
        cls._parse = delegate._parse

    @classmethod
    def _parse(cls, ctx, text, pos):
        cls._init_fields()
        return cls._parse(ctx, text, pos)

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
    def _parse(cls, ctx, text, pos):
        if isinstance(text, str):
            return cls._parse_str(text, pos)
        else:
            return cls._parse_item(ctx, text, pos)

    @classmethod
    def _parse_str(cls, text, pos):
        result = yield Step(cls.pattern, pos)
        if isinstance(result, Success):
            token = cls(result.value, pos)
            yield Success(token, result.pos)
        else:
            yield result

    @classmethod
    def _parse_item(cls, ctx, text, pos):
        delegate = Require(Any, lambda x: isinstance(x, cls))
        cls._parse_item = delegate._parse
        return delegate._parse(ctx, text, pos)

    def __eq__(self, other):
        if isinstance(other, str):
            return self.value == other
        else:
            return isinstance(other, Token) and self.value == other.value


def TokenClass(pattern, is_ignored=False):
    class TokenClass(Token):
        def __repr__(self):
            name = self.__class__.__name__
            if name == 'TokenClass':
                name = 'Token'
            return f'{name}({self.value!r}, pos={self.pos})'
    TokenClass.pattern = conv(pattern)
    TokenClass._is_ignored = is_ignored
    return TokenClass


def TokenPattern(pattern, is_ignored=False):
    return TokenClass(Regex(pattern), is_ignored=is_ignored)


def Tokenizer(*exprs):
    return Left(List(Choice(*exprs)), End)


class Transform(Expr):
    def __init__(self, expr, func):
        self.expr = expr
        self.func = func

    def _parse(self, ctx, text, pos):
        result = yield Step(self.expr, pos)
        if isinstance(result, Success):
            value = self.func(result.value)
            yield Success(value, result.pos)
        else:
            yield result

    def __repr__(self):
        return f'Transform({self.expr!r})'

InfixOp = namedtuple('InfixOp', 'left, operator, right')
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


def transform(tree, *callbacks):
    if not callbacks:
        return tree

    if len(callbacks) == 1:
        callback = callbacks[0]
    else:
        def callback(tree):
            for f in callbacks:
                tree = f(tree)
            return tree

    return _transform(tree, callback)


def _transform(tree, callback):
    if isinstance(tree, list):
        return [_transform(x, callback) for x in tree]

    if isinstance(tree, Token):
        return callback(tree)

    if not isinstance(tree, (InfixOp, PostfixOp, PrefixOp, Struct)):
        return tree

    has_changes = False
    updates = {}
    for field in tree._fields:
        was = getattr(tree, field)
        now = _transform(was, callback)
        updates[field] = now
        if not has_changes and was is not now:
            has_changes = True

    if has_changes:
        tree = tree._replace(**updates)

    return callback(tree)


Step = namedtuple('Step', 'expr, pos')


class Success(namedtuple('Success', 'value, pos')):
    @property
    def is_success(self):
        return True


class Failure(namedtuple('Failure', 'expr, pos')):
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
