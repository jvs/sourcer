from collections import namedtuple
from functools import reduce
import re
import types
import typing


def parse(expr, text, pos=0, max_errors=16):
    result, errors = _parse(expr, text, pos, max_errors)
    if errors:
        raise ParseError(result, errors)
    else:
        return result.value



def _parse(expr, text, pos, max_errors):
    expr = conv(expr)
    ctx = ParsingContext()

    current_result = _parse_once(ctx, expr, text, pos)
    errors = []

    if not current_result.is_success:
        _clear_memo_table(ctx.memo, current_result)

    base_memo = dict(ctx.memo)


    while max_errors > 0:
        max_errors -= 1

        if current_result.is_success:
            break

        replacement = current_result
        best_result = current_result
        best_error = (current_result, None)
        recovery_rules = current_result.recovery_rules

        if not recovery_rules:
            recovery_rules = [SkipTo(current_result.expr), Pass(None)]

        for recovery in recovery_rules:
            ctx.memo = dict(base_memo)

            # Get the replacement value from the recovery rule.
            replacement = _parse_once(ctx, recovery, text, current_result.pos)

            # If we couldn't get a value for this recovery rule, then just skip it.
            if not replacement.is_success:
                continue

            # Install the replacement.
            ctx.memo[current_result.pos, current_result.expr] = replacement
            next_result = _parse_once(ctx, expr, text, pos)

            if best_result.pos < next_result.pos or next_result.is_success:
                best_result = next_result
                best_error = (current_result, replacement)

            # If we successfully parsed the text, then just stop here.
            if next_result.is_success:
                break

        current_result = best_result
        errors.append(best_error)

    return (current_result, errors)


def _parse_once(ctx, expr, text, pos):
    memo = ctx.memo
    result = None

    key = (pos, expr)
    generator = expr._parse(ctx, text, pos)
    stack = [(key, generator)]

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

    return result


def _clear_memo_table(memo, prev_result):
    pos = prev_result.pos
    expr = prev_result.expr
    for key, value in list(memo.items()):
        # if key[0] == pos or memo[key] is prev_result or memo[key].pos == pos:
        # if memo[key] is prev_result:
        if not value.is_success and value.pos == pos and value.expr is expr:
            del memo[key]


class ParsingContext:
    def __init__(self):
        self.memo = {}
        self.commits = []


class ParseError(Exception):
    """Indicates that the `parse` function failed."""
    def __init__(self, result, errors):
        super().__init__()
        self.result = result
        self.errors = errors


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
            raise Exception('Parser does not have any token definitions.')

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
        if not hasattr(self, '_delegate'):
            self._delegate = self.derive()
        yield (yield Step(self._delegate, pos))
        # yield result
        # self._parse = delegate._parse
        # return delegate._parse(ctx, text, pos)


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
            if next_result.is_error:
                yield result
                return
            elif best_failure.pos < next_result.pos:
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
            if item.is_error:
                yield item
                return
            if not item.is_success:
                break
            result.append(item.value)
            pos = item.pos
            result_pos = pos
            skipped = yield Step(self.separator, pos)
            if skipped.is_error:
                yield skipped
                return
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


class Assert(Expr):
    def __init__(self, expr):
        self.expr = conv(expr)

    def _parse(self, ctx, text, pos):
        result = yield Step(self.expr, pos)
        if result.is_success or not result.is_error:
            yield result
        else:
            yield result.as_error()

    def __repr__(self):
        return f'Assert({self.expr!r})'


class Checkpoint(Expr):
    def __init__(self, expr):
        self.expr = conv(expr)

    def __call__(self, *a, **k):
        return self.expr.__call__(*a, **k)

    def _parse(self, ctx, text, pos):
        ctx.commits.append(False)
        result = yield Step(self.expr, pos)
        saw_commit = ctx.commits.pop()

        if result.is_success or result.is_error or not saw_commit:
            yield result
        else:
            yield result.as_error()

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

    def _eval(self):
        if not hasattr(self, 'value'):
            self.value = conv(self.func())
        return self.value

    def derive(self):
        return self._eval()

    # def __repr__(self):
        # return f'Lazy(lambda: {self.value!r})' if has


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
            if item.is_error:
                yield item
                return
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
            # return self._delegate._parse(ctx, text, pos)
            return self._parse_item(pos)

    def _parse_str(self, text, pos):
        if not isinstance(self.value, str):
            yield Failure(self, pos)
            return

        end = pos + len(self.value)
        if end <= len(text) and self.value == text[pos:end]:
            yield Success(self.value, end)
        else:
            yield Failure(self, pos)

    def _parse_item(self, pos):
        result = yield Step(self._delegate, pos)
        yield result

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


class Recover(Expr):
    def __init__(self, expr):
        self.expr = conv(expr)
        self.recovery_rules = []

    def __call__(self, *a, **k):
        return self.expr.__call__(*a, **k)

    def _parse(self, ctx, text, pos):
        result = yield Step(self.expr, pos)
        if not result.is_success:
            result.recovery_rules.extend(self.recovery_rules)
        yield result


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

    def __repr__(self):
        return f'Require({self.expr!r}, {self.pred})'

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

    def __repr__(self):
        parts = ', '.join(repr(x) for x in self.exprs)
        return f'Seq({parts})'

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
        # cls._parse = delegate._parse
        cls._delegate = delegate

    @classmethod
    def _parse(cls, ctx, text, pos):
        if not hasattr(cls, '_delegate'):
            cls._init_fields()
        result = yield Step(cls._delegate, pos)
        yield result
        # cls._init_fields()
        # return cls._parse(ctx, text, pos)

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
        if not hasattr(cls, '_delegate'):
            cls._delegate = Require(Any, lambda x: isinstance(x, cls))
        result = yield Step(cls._delegate, pos)
        yield result
        # cls._parse_item = delegate._parse
        # return delegate._parse(ctx, text, pos)

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
    if isinstance(tree, (InfixOp, PostfixOp, PrefixOp, Token, Struct)):
        yield tree

    if isinstance(tree, (list, InfixOp, PostfixOp, PrefixOp)):
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

    @property
    def is_error(self):
        return False



class Failure:
    def __init__(self, expr, pos, is_error=False):
        self.expr = expr
        self.pos = pos
        self.is_error = is_error
        self.recovery_rules = []

    def __repr__(self):
        return f'Failure({self.expr!r}, {self.pos!r}, {self.is_error!r})'

    @property
    def is_success(self):
        return False

    def as_error(self):
        if self.is_error:
            return self
        else:
            result = Failure(self.expr, self.pos, is_error=True)
            result.recovery_rules = list(self.recovery_rules)
            return result


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
