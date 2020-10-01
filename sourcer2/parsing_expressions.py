import io
import typing
from string import Template

from .program_builder import ProgramBuilder, Raw, Return, Tup, Val, Var, Yield


POS = Raw('_pos')
RESULT = Raw('_result')
STATUS = Raw('_status')
TEXT = Raw('_text')

CONTINUE = 3


class Expr:
    program_id = None

    def matches_atomically(self):
        return False

    def compile(self, pb):
        if self.program_id is None:
            self.program_id = pb.reserve_id()

        if pb.has_available_blocks(self.num_blocks):
            self._compile(pb)
        else:
            # TODO: Check if the call stack and see if there's room for a call here.
            # If not, then use the "yield" setup.
            name = f'_parsing_expression_{self.program_id}'
            # TODO: See if the expression uses any of the current rule's parameters.
            # Use "visit()" to find all the free variables...
            with pb.global_function(name, (str(TEXT), str(POS))):
                self._compile(pb)
                pb(Return(Tup(STATUS, RESULT, POS)))

            func = Raw(name)
            pb(Tup(STATUS, RESULT, POS) << func(TEXT, POS))


def visit(callback, expr):
    if isinstance(expr, Expr):
        callback(expr)
        for child in expr.__dict__.values():
            visit(callback, child)

    elif isinstance(expr, (list, tuple)):
        for child in expr:
            visit(callback, child)


class Alt(Expr):
    num_blocks = 2

    def __init__(self, expr, separator, allow_trailer=False, allow_empty=True):
        self.expr = expr
        self.separator = separator
        self.allow_trailer = allow_trailer
        self.allow_empty = allow_empty

    def _compile(self, pb):
        staging = pb.var('staging', Val([]))
        checkpoint = pb.var('checkpoint', POS)

        with pb.loop():
            self.expr.compile(pb)

            with pb.IF_NOT(STATUS):
                pb(Raw('break'))

            staging.append(RESULT)
            pb(checkpoint << POS)
            self.separator.compile(pb)

            with pb.IF_NOT(STATUS):
                pb(Raw('break'))

            if self.allow_trailer:
                pb(checkpoint << POS)

        success = [
            RESULT << staging,
            STATUS << True,
            POS << checkpoint,
        ]

        if self.allow_empty:
            pb(*success)
        else:
            with pb.IF(staging):
                pb(*success)


class Apply(Expr):
    num_blocks = 2

    def __init__(self, expr1, expr2, apply_left=False):
        self.expr1 = expr1
        self.expr2 = expr2
        self.apply_left = apply_left

    def _compile(self, pb):
        self.expr1.compile(pb)

        with pb.IF(STATUS):
            first = pb.var('func' if self.apply_left else 'arg', RESULT)
            self.expr2.compile(pb)

            with pb.IF(STATUS):
                result = first(RESULT) if self.apply_left else RESULT(first)
                pb(RESULT << result)


class Call(Expr):
    def __init__(self, func, args):
        self.func = func
        self.args = args

    def _compile(self, pb):
        args, kwargs = [], []

        for arg in self.args:
            is_kw = isinstance(arg, KeywordArg)
            expr = arg.expr if is_kw else arg

            if isinstance(expr, Ref):
                value = Raw(f'_parse_{expr.name}')


class Choice(Expr):
    num_blocks = 2

    def __init__(self, *exprs):
        self.exprs = exprs

    def matches_atomically(self):
        return all(x.matches_atomically() for x in self.exprs)

    def _compile(self, pb):
        backtrack = Var('backtrack')
        farthest_pos = Var('farthest_pos')

        pb(backtrack << farthest_pos << POS)

        farthest_expr = pb.var('farthest_expr', Val(self.program_id))

        with pb.breakable():
            for i, expr in enumerate(self.exprs):
                expr.compile(pb)

                with pb.IF(STATUS):
                    pb(Raw('break'))

                if not expr.matches_atomically():
                    with pb.IF(farthest_pos < POS):
                        pb(farthest_pos << POS)
                        pb(farthest_expr << Val(expr.program_id))

                    if i + 1 < len(self.exprs):
                        pb(POS << backtrack)

            pb(POS << farthest_pos)
            pb(RESULT << Val(self.program_id))


class Class(Expr):
    num_blocks = 2

    def __init__(self, name, params, fields, is_ignored=False):
        self.name = name
        self.params = params
        self.fields = fields
        self.is_ignored = is_ignored

    def _compile(self, pb):
        buf = io.StringIO()
        write = buf.write
        write(f'\nclass {self.name}(Node):\n')

        names = tuple(x.name for x in self.fields)
        write(f'    _fields = {names!r}\n\n')

        init_params = ', '.join(x.name for x in self.fields)
        write(f'    def __init__(self, {init_params}):\n')
        for field in self.fields:
            write(f'        self.{field.name} = {field.name}\n')
        write('\n')

        write(f'    def __repr__(self):\n')
        inits = ', '.join(f'{x.name}={{self.{x.name}!r}}' for x in self.fields)
        write(f'        return f\'{self.name}({inits})\'\n\n')

        pb._globals.append(Raw(buf.getvalue()))

        exprs = (x.expr for x in self.fields)
        seq = Seq(*exprs, names=names, constructor=self.name)
        seq.compile(pb)


class Discard(Expr):
    num_blocks = 2

    def __init__(self, expr1, expr2, discard_left=True):
        self.expr1 = expr1
        self.expr2 = expr2
        self.discard_left = discard_left

    def _compile(self, pb):
        with pb.breakable():
            self.expr1.compile(pb)

            with pb.IF_NOT(STATUS):
                pb(Raw('break'))

            if self.discard_left:
                self.expr2.compile(pb)
            else:
                staging = pb.var('staging', RESULT)
                self.expr2.compile(pb)

                with pb.IF(STATUS):
                    pb(RESULT << staging)


class Expect(Expr):
    num_blocks = 0

    def __init__(self, expr):
        self.expr = expr

    def matches_atomically(self):
        return self.expr.matches_atomically()

    def _compile(self, pb):
        backtrack = pb.var('backtrack', POS)
        self.expr.compile(pb)
        pb(POS << backtrack)


class ExpectNot(Expr):
    num_blocks = 1

    def __init__(self, expr):
        self.expr = expr

    def matches_atomically(self):
        return self.expr.matches_atomically()

    def _compile(self, pb):
        backtrack = pb.var('backtrack', POS)
        self.expr.compile(pb)
        pb(POS << backtrack)

        with pb.IF(STATUS):
            pb(STATUS << False)
            pb(RESULT << Val(self.program_id))

        with pb.ELSE():
            pb(STATUS << True)
            pb(RESULT << Val(None))


class Fail(Expr):
    num_blocks = 0

    def __init__(self, message):
        self.message = None

    def _compile(self, pb):
        pb(
            STATUS << False,
            RESULT << Val(self.program_id),
        )


class KeywordArg(Expr):
    def __init__(self, name, expr):
        self.name = name
        self.expr = expr


def Left(expr1, expr2):
    return Discard(expr1, expr2, discard_left=False)


class LetExpression(Expr):
    num_blocks = 1

    def __init__(self, name, expr, body):
        self.name = name
        self.expr = expr
        self.body = body

    def _compile(self, pb):
        self.expr.compile(pb)

        with pb.IF(STATUS):
            pb(Raw(self.name) << RESULT)
            self.body.compile(pb)


class List(Expr):
    num_blocks = 2

    def __init__(self, expr, allow_empty=True):
        self.expr = expr
        self.allow_empty = allow_empty

    def _compile(self, pb):
        staging = pb.var('staging', Raw('[]'))

        with pb.loop():
            checkpoint = pb.var('checkpoint', POS)
            self.expr.compile(pb)

            with pb.IF(STATUS):
                pb(
                    staging.append(RESULT),
                    Raw('continue'),
                )

            with pb.ELSE():
                pb(
                    POS << checkpoint,
                    Raw('break'),
                )

        success = [
            RESULT << staging,
            STATUS << True,
        ]

        if self.allow_empty:
            pb(*success)
        else:
            with pb.IF(staging):
                pb(*success)


class Opt(Expr):
    num_blocks = 1

    def __init__(self, expr):
        self.expr = expr

    def matches_atomically(self):
        return True

    def _compile(self, pb):
        backtrack = pb.var('backtrack', POS)
        self.expr.compile(pb)
        with pb.IF_NOT(STATUS):
            out(
                STATUS << True,
                POS << backtrack,
                RESULT << None,
            )


class Pass(Expr):
    num_blocks = 0

    def __init__(self, value):
        self.value = value

    def matches_atomically(self):
        return True

    def _compile(self, pb):
        pb(
            STATUS << True,
            RESULT << Val(self.value),
        )


class Ref(Expr):
    num_blocks = 0

    def __init__(self, name):
        self.name = name

    def _compile(self, pb):
        func_name = f'_parse_{self.name}'
        pb(Tup(STATUS, RESULT, POS) << Yield(Tup(CONTINUE, Raw(func_name), POS)))


class RegexLiteral(Expr):
    num_blocks = 1

    def __init__(self, pattern):
        if isinstance(pattern, typing.Pattern):
            pattern = pattern.pattern
        if not isinstance(pattern, str):
            raise TypeError('Expected str')
        self.pattern = pattern
        self.skip_ignored = False

    def matches_atomically(self):
        return True

    def _compile(self, pb):
        pb.add_import('from re import compile as compile_re')
        matcher = pb.define_global('matcher', f'compile_re({self.pattern!r}).match')
        match = pb.var('match', matcher(TEXT, POS))
        end = match.end()

        with pb.IF(match):
            pb(
                POS << (_skip_ignored(end) if self.skip_ignored else end),
                STATUS << True,
                RESULT << match.group(0),
            )

        with pb.ELSE():
            pb(STATUS << False)
            pb(RESULT << Val(self.program_id))


def Right(expr1, expr2):
    return Discard(expr1, expr2, discard_left=True)


class Rule(Expr):
    num_blocks = 1

    def __init__(self, name, params, expr, is_ignored=False):
        self.name = name
        self.params = params
        self.expr = expr
        self.is_ignored = is_ignored

    def _compile(self, pb):
        name = f'_parse_{self.name}'
        params = [str(TEXT), str(POS)] + (self.params or [])

        with pb.global_function(name, params):
            self.expr.compile(pb)
            pb(Yield(Tup(STATUS, RESULT, POS)))


class Seq(Expr):
    num_blocks = 2

    def __init__(self, *exprs, names=None, constructor=None):
        if isinstance(constructor, type):
            constructor = constructor.__name__
        self.exprs = exprs

        if names is not None:
            if len(names) != len(exprs):
                raise Exception('Expected same number of expressions and names.')
            self.names = names
        else:
            self.names = [None] * len(exprs)

        self.constructor = constructor

    def _compile(self, pb):
        with pb.breakable():
            items = []
            for name, expr in zip(self.names, self.exprs):
                expr.compile(pb)

                with pb.IF_NOT(STATUS):
                    pb(Raw('break'))

                item = Var('item') if name is None else Raw(name)
                pb(item << RESULT)
                items.append(item)

            ctor = Tup if self.constructor is None else Raw(self.constructor)
            pb(RESULT << ctor(*items))


class Skip(Expr):
    num_blocks = 2

    def __init__(self, *exprs):
        self.exprs = exprs

    def _compile(self, pb):
        checkpoint = Var('checkpoint')

        with pb.breakable():
            pb(checkpoint << POS)
            for expr in self.exprs:
                expr.compile(pb)

                with pb.IF(STATUS):
                    pb(Raw('continue'))

                with pb.ELSE():
                    pb(POS << checkpoint)

        pb(
            STATUS << Val(True),
            RESULT << Val(None),
        )


def Some(expr):
    return List(expr, allow_empty=False)


class StringLiteral(Expr):
    def __init__(self, value):
        if not isinstance(value, str):
            raise TypeError(f'Expected str. Received: {type(value)}.')
        self.value = value
        self.skip_ignored = False
        self.num_blocks = 0 if self.value == '' else 1

    def matches_atomically(self):
        return True

    def _compile(self, pb):
        if self.value == '':
            pb(
                STATUS << Val(True),
                RESULT << Val(''),
            )
            return

        value = pb.var('value', Val(self.value))
        end = pb.var('end', POS + len(self.value))

        with pb.IF(TEXT[POS >> end] == value):
            pb(
                POS << (_skip_ignored(end) if self.skip_ignored else end),
                STATUS << True,
                RESULT << value,
            )

        with pb.ELSE():
            pb(STATUS << False)


class OperatorPrecedence(Expr):
    def __init__(self, atom, *rules):
        self.atom = atom
        self.rules = rules


# class LeftAssoc(OperatorPrecedenceRule):
#     pass


# class NonAssoc(LeftAssoc):
#     pass


# class RightAssoc(OperatorPrecedenceRule):
#     pass


# class Postfix(OperatorPrecedenceRule):
#     pass


# class Prefix(OperatorPrecedenceRule):
#     pass


class PythonExpression(Expr):
    num_blocks = 0

    def __init__(self, source_code):
        self.source_code = source_code

    def _compile(self, pb):
        pb(
            RESULT << Raw(self.source_code),
            STATUS << True,
        )


class PythonSection(Expr):
    def __init__(self, source_code):
        self.source_code = source_code


class Where(Expr):
    num_blocks = 2

    def __init__(self, expr, predicate):
        self.expr = expr
        self.predicate = predicate

    def _compile(self, pb):
        self.expr.compile(pb)

        with pb.IF(STATUS):
            arg = pb.var('arg', RESULT)
            self.predicate.compile(pb)

            with pb.IF(STATUS):
                with pb.IF(RESULT(arg)):
                    pb(RESULT << arg)

                with pb.ELSE():
                    pb(STATUS << False)
                    pb(RESULT << Val(self.program_id))


def _skip_ignored(pos):
    return Yield(Tup(CONTINUE, Raw('_parse__ignored'), pos))[2]


def generate_source_code(nodes):
    pb = ProgramBuilder()
    pb.add_import('from collections import namedtuple as _nt')
    pb(Raw(_program_setup))

    # Collect all the rules and stuff.
    rules, ignored = [], []
    start_rule = None

    for node in nodes:
        # Just add Python sections directly to the program.
        if isinstance(node, (PythonExpression, PythonSection)):
            pb(Raw(node.source_code))
            continue

        rules.append(node)

        if node.is_ignored:
            ignored.append(node)

        if start_rule is None and node.name.lower() == 'start':
            start_rule = node

    if start_rule is not None and start_rule.is_ignored:
        raise Exception(
            f'The {start_rule!r} rule may not have the "ignored" modifier.'
        )

    if not rules:
        raise Exception('Expected one or more grammar rules.')

    visited_names = set()
    for rule in rules:
        if rule.name.startswith('_'):
            raise Exception(
                'Grammar rule names must start with a letter. Found a rule that'
                f' starts with an underscore: "{rule.name}". '
            )
        if rule.name in visited_names:
            raise Exception(
                'Each grammar rule must have a unique name. Found two or more'
                f' rules named "{rule.name}".'
            )
        visited_names.add(rule.name)

    default_rule = start_rule or rules[0]
    pb(Raw(Template(_main_template).substitute(
        CONTINUE=CONTINUE,
        start=f'_parse_{start_rule.name}',
    )))

    if ignored:
        # Create a rule called "_ignored" that skips all the ignored rules.
        refs = [Ref(x.name) for x in ignored]
        rules.append(Rule('_ignored', None, Skip(*refs)))

        # If we have a start rule, then update its expression to skip ahead past
        # any leading ignored stuff.
        if isinstance(start_rule, Class):
            first_rule = start_rule.fields[0] if start_rule.fields else None
        else:
            first_rule = start_rule

        if first_rule:
            assert isinstance(first_rule, Rule)
            first_rule.expr = Right(Ref('_ignored'), first_rule.expr)

        # Update the "skip_ignored" flag of each StringLiteral and RegexLiteral.
        def _set_skip_ignored(expr):
            if hasattr(expr, 'skip_ignored'):
                expr.skip_ignored = True

        for rule in rules:
            if not rule.is_ignored:
                visit(_set_skip_ignored, rule)

    for rule in rules:
        rule.compile(pb)

    return pb.generate_source_code()


_program_setup = r'''
class Node:
    _fields = ()

    def __eq__(self, other):
        if not isinstance(other, self.__class__):
            return False
        for field in self._fields:
            if getattr(self, field) != getattr(other, field):
                return False
        return True

    def _asdict(self):
        return {k: getattr(self, k) for k in self._fields}

    def _replace(self, **kw):
        for field in self._fields:
            if field not in kw:
                kw[field] = getattr(self, field)
        return self.__class__(**kw)
'''


_main_template = r'''
class ParseError(Exception):
    def __init__(self, expr_code, pos):
        self.expr_code = expr_code
        self.pos = pos


class Infix(Node):
    _fields = ('left', 'operator', 'right')

    def __init__(self, left, operator, right):
        self.left = left
        self.operator = operator
        self.right = right

    def __repr__(self):
        return f'Infix({self.left!r}, {self.operator!r}, {self.right!r})'


class Postfix(Node):
    _fields = ('left', 'operator')

    def __init__(self, left, operator):
        self.left = left
        self.operator = operator

    def __repr__(self):
        return f'Postfix({self.left!r}, {self.operator!r})'


class Prefix(Node):
    _fields = ('operator', 'right')

    def __init__(self, operator, right):
        self.operator = operator
        self.right = right

    def __repr__(self):
        return f'Prefix({self.operator!r}, {self.right!r})'


def parse(text, pos=0):
    return _run(text, pos, $start)


class _RuleClosure(_nt('_RuleClosure', 'rule, args, kwargs')):
    def __call__(self, _text, _pos):
        return self.rule(_text, _pos, *self.args, **dict(self.kwargs))


class _StringLiteral(str):
    def __call__(self, _text, _pos):
        return self._parse_function(_text, _pos)


def _run(text, pos, start):
    memo = {}
    result = None

    key = ($CONTINUE, start, pos)
    gtor = start(text, pos)
    stack = [(key, gtor)]

    while stack:
        key, gtor = stack[-1]
        result = gtor.send(result)

        if result[0] != $CONTINUE:
            stack.pop()
            memo[key] = result
        elif result in memo:
            result = memo[result]
        else:
            gtor = result[1](text, result[2])
            stack.append((result, gtor))
            result = None

    if result[0]:
        return result[1]
    else:
        raise ParseError(result[1], result[2])


def visit(node):
    if isinstance(node, list):
        yield from node

    elif isinstance(node, Node):
        yield node

        if hasattr(node, '_fields'):
            for field in node._fields:
                yield from visit(getattr(node, field))


def transform(node, *callbacks):
    if not callbacks:
        return node

    if len(callbacks) == 1:
        callback = callbacks[0]
    else:
        def callback(node):
            for f in callbacks:
                node = f(node)
            return node

    return _transform(node, callback)


def _transform(node, callback):
    if isinstance(node, list):
        return [_transform(x, callback) for x in node]

    if not isinstance(node, Node):
        return node

    updates = {}
    for field in node._fields:
        was = getattr(node, field)
        now = _transform(was, callback)
        if was is not now:
            updates[field] = now

    if updates:
        node = node._replace(**updates)

    return callback(node)

'''
