from collections import defaultdict
import typing
from string import Template

from .program_builder import (
    Binop, LIST, ProgramBuilder, Raw, Return, Tup, Val, Var, Yield,
)


class _RawBuilder:
    def __getattr__(self, name):
        return Raw(name)


raw = _RawBuilder()


POS = Raw('_pos')
RESULT = Raw('_result')
STATUS = Raw('_status')
TEXT = Raw('_text')

BREAK = Raw('break')
CONTINUE = Raw('continue')

CALL = 3


class Expr:
    def matches_atomically(self):
        return False

    def compile(self, pb):
        if pb.has_available_blocks(self.num_blocks):
            self._compile(pb)
        else:
            func, params = _functionalize(self, is_generator=False)
            pb(Tup(STATUS, RESULT, POS) << func(*params))


def _functionalize(pb, expr, is_generator=False):
    name = f'_parse_function_{expr.program_id}'
    params = [str(TEXT), str(POS)] + list(sorted(_freevars(expr)))
    with pb.global_function(name, params):
        expr._compile(pb)
        cls = Yield if is_generator else Return
        pb(cls(Tup(STATUS, RESULT, POS)))
    return Raw(name), [Raw(x) for x in params]


def visit(previsit, expr, postvisit=None):
    if isinstance(expr, Expr):
        previsit(expr)

        for child in expr.__dict__.values():
            visit(previsit, child, postvisit)

        if postvisit:
            postvisit(expr)

    elif isinstance(expr, (list, tuple)):
        for child in expr:
            visit(previsit, child, postvisit)


class Alt(Expr):
    num_blocks = 2

    def __init__(self, expr, separator, allow_trailer=False, allow_empty=True):
        self.expr = expr
        self.separator = separator
        self.allow_trailer = allow_trailer
        self.allow_empty = allow_empty

    def _compile(self, pb):
        staging = pb.var('staging', Raw('[]'))
        checkpoint = pb.var('checkpoint', POS)

        with pb.loop():
            self.expr.compile(pb)

            with pb.IF_NOT(STATUS):
                pb(BREAK)

            pb(staging.append(RESULT))
            pb(checkpoint << POS)
            self.separator.compile(pb)

            with pb.IF_NOT(STATUS):
                pb(BREAK)

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
    num_blocks = 0

    def __init__(self, func, args):
        self.func = func
        self.args = args

    def _compile(self, pb):
        args, kwargs = [], []

        for arg in self.args:
            is_kw = isinstance(arg, KeywordArg)
            expr = arg.expr if is_kw else arg

            if isinstance(expr, Ref):
                value = Raw(expr.name)
            elif isinstance(expr, PythonExpression):
                value = Raw(expr.source_code)
            else:
                func, params = _functionalize(pb, expr, is_generator=True)
                if len(params) > 2:
                    value = raw._ParseFunction(func, Tup(*params[-2]), Tup())
                    value = pb.var('arg', value)
                else:
                    value = func

                if isinstance(expr, StringLiteral):
                    value = raw._wrap_string_literal(Val(expr.value), value)
                    value = pb.var('arg', value)

            if is_kw:
                kwargs.append(Tup(Val(arg.name, value)))
            else:
                args.append(value)

        func = raw._ParseFunction(Raw(self.func.name), Tup(*args), Tup(*kwargs))
        func = pb.var('func', func)
        pb(Tup(STATUS, RESULT, POS) << Yield(Tup(CALL, func, POS)))


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
                    pb(BREAK)

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
        field_names = [x.name for x in self.fields]
        parse_func = Raw(f'{_cont_name(self.name)}')

        with pb.global_class(self.name, 'Node'):
            pb(raw._fields << Tup(*[Val(x) for x in field_names]))

            with pb.local_function('__init__', ['self'] + field_names):
                for name in field_names:
                    pb(Raw(f'self.{name} = {name}'))

            with pb.local_function('__repr__', ['self']):
                values = ', '.join(f'{x}={{self.{x}!r}}' for x in field_names)
                pb(Return(Raw(f"f'{self.name}({values})'")))

            pb(Raw('@staticmethod'))
            if self.params:
                with pb.local_function('parse', self.params):
                    args = Tup(*self.params)
                    kwargs = Raw('{}')
                    pb(raw.closure << raw._ParseFunction(parse_func, args, kwargs))
                    pb(Return(Raw('lambda text, pos=0: _run(text, pos, closure)')))
            else:
                with pb.local_function('parse', ['text', 'pos=0']):
                    pb(Return(Raw(f'_run(text, pos, {parse_func})')))

        params = [str(TEXT), str(POS)] + (self.params or [])
        with pb.global_function(parse_func, params):
            exprs = (x.expr for x in self.fields)
            seq = Seq(*exprs, names=field_names, constructor=self.name)
            seq.compile(pb)
            pb(Yield(Tup(STATUS, RESULT, POS)))


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
                pb(BREAK)

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
            pb(STATUS << Val(False))
            pb(RESULT << Val(self.program_id))

        with pb.ELSE():
            pb(STATUS << Val(True))
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
                pb(staging.append(RESULT), CONTINUE)

            with pb.ELSE():
                pb(POS << checkpoint, BREAK)

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
            pb(
                STATUS << Val(True),
                POS << backtrack,
                RESULT << Val(None),
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
        self.is_local = False

    def _compile(self, pb):
        pb(Tup(STATUS, RESULT, POS) << Yield(Tup(CALL, Raw(self.name), POS)))


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
        params = [str(TEXT), str(POS)] + (self.params or [])

        cont_name = _cont_name(self.name)
        entry_name = _entry_name(self.name)

        with pb.global_function(cont_name, params):
            self.expr.compile(pb)
            pb(Yield(Tup(STATUS, RESULT, POS)))

        with pb.global_function(entry_name, ['text', 'pos=0']):
            pb(Return(Raw(f'_run(text, pos, {cont_name})')))

        with pb.global_section():
            pb(Raw(f'{self.name} = Rule({self.name!r}, {entry_name})'))


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
                    pb(BREAK)

                item = Var('item') if name is None else Raw(name)
                pb(item << RESULT)
                items.append(item)

            ctor = LIST if self.constructor is None else Raw(self.constructor)
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
                    pb(CONTINUE)

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
            pb(STATUS << False, RESULT << Val(self.program_id))


class OperatorPrecedence(Expr):
    def __init__(self, atom, *rules):
        self.atom = atom
        self.rules = rules
        self.num_blocks = (rules[-1] if rules else atom).num_blocks

    def _compile(self, pb):
        prev = self.atom
        for rule in self.rules:
            rule.operand = prev
            prev = rule
        prev.compile(pb)


class OperatorPrecedenceRule(Expr):
    def __init__(self, *operators):
        self.operators = operators[0] if len(operators) == 1 else Choice(*operators)
        self.operand = None


class LeftAssoc(OperatorPrecedenceRule):
    num_blocks = 2

    def _compile(self, pb):
        is_first = pb.var('is_first', Val(True))
        staging = pb.var('staging', Val(None))
        operator = Var('operator')

        with pb.loop():
            self.operand.compile(pb)

            with pb.IF_NOT(STATUS):
                pb(BREAK)

            checkpoint = pb.var('checkpoint', POS)

            with pb.IF(is_first):
                pb(is_first << Val(False))
                pb(staging << RESULT)

            with pb.ELSE():
                pb(staging << raw.Infix(staging, operator, RESULT))
                if isinstance(self, NonAssoc):
                    pb(BREAK)

            self.operators.compile(pb)

            with pb.IF_NOT(STATUS):
                pb(BREAK)

            pb(operator << RESULT)

        with pb.IF_NOT(is_first):
            pb(
                STATUS << Val(True),
                RESULT << staging,
                POS << checkpoint,
            )


class NonAssoc(LeftAssoc):
    pass


class RightAssoc(OperatorPrecedenceRule):
    num_blocks = 4

    def _compile(self, pb):
        backup = pb.var('backup', Val(None))
        prev = pb.var('prev', Val(None))

        staging = Var('staging')
        checkpoint = Var('checkpoint')

        with pb.loop():
            self.operand.compile(pb)

            with pb.IF_NOT(STATUS):
                with pb.IF(prev):
                    with pb.IF(backup):
                        pb(backup.right << prev.left, RESULT << staging)
                    with pb.ELSE():
                        pb(RESULT << prev.left)
                    pb(STATUS << Val(True), POS << checkpoint)
                pb(BREAK)

            pb(checkpoint << POS)
            operand = pb.var('operand', RESULT)
            self.operators.compile(pb)

            with pb.IF_NOT(STATUS):
                with pb.IF(prev):
                    pb(prev.right << operand, RESULT << staging)

                with pb.ELSE():
                    pb(RESULT << operand)

                pb(STATUS << Val(True), POS << checkpoint, BREAK)

            step = raw.Infix(operand, RESULT, Val(None))

            with pb.IF(prev):
                pb(backup << prev, backup.right << prev << step)

            with pb.ELSE():
                pb(staging << prev << step)


class Postfix(OperatorPrecedenceRule):
    num_blocks = 3

    def _compile(self, pb):
        self.operand.compile(pb)

        with pb.IF(STATUS):
            staging = pb.var('staging', RESULT)
            checkpoint = pb.var('checkpoint', POS)

            with pb.loop():
                self.operators.compile(pb)

                with pb.IF(STATUS):
                    pb(staging << raw.Postfix(staging, RESULT))
                    pb(checkpoint << POS)

                with pb.ELSE():
                    pb(
                        STATUS << Val(True),
                        RESULT << staging,
                        POS << checkpoint,
                        BREAK,
                    )


class Prefix(OperatorPrecedenceRule):
    num_blocks = 2

    def _compile(self, pb):
        prev = pb.var('prev', Val(None))
        checkpoint = pb.var('checkpoint', POS)
        staging = Var('staging')

        with pb.loop():
            self.operators.compile(pb)

            with pb.IF_NOT(STATUS):
                pb(POS << checkpoint, BREAK)

            pb(checkpoint << POS)
            step = pb.var('step', raw.Prefix(RESULT, Val(None)))

            with pb.IF(Binop(prev, 'is', Val(None))):
                pb(prev << staging << step)

            with pb.ELSE():
                pb(prev.right << step, prev << step)

        self.operand.compile(pb)

        with pb.IF(Binop(STATUS, 'and', prev)):
            pb(prev.right << RESULT, RESULT << staging)


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
    return Yield(Tup(CALL, Raw(_cont_name('_ignored')), pos))[2]


def _cont_name(name):
    return f'_cont_{name}'


def _entry_name(name):
    return f'_parse_{name}'


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
            first_rule.expr = Right(Ref(_cont_name('_ignored')), first_rule.expr)

        # Update the "skip_ignored" flag of each StringLiteral and RegexLiteral.
        def _set_skip_ignored(expr):
            if hasattr(expr, 'skip_ignored'):
                expr.skip_ignored = True

        for rule in rules:
            if not rule.is_ignored:
                visit(_set_skip_ignored, rule)

    _assign_ids(rules)
    _update_local_references(rules)
    _update_rule_references(rules)

    default_rule = start_rule or rules[0]

    pb(Raw(Template(_main_template).substitute(
        CALL=CALL,
        start=_cont_name(default_rule.name),
    )))

    for rule in rules:
        rule.compile(pb)

    return pb.generate_source_code()


def _assign_ids(rules):
    next_id = 1
    def assign_id(node):
        nonlocal next_id
        node.program_id = next_id
        next_id += 1
    visit(assign_id, rules)


class _SymbolCounter:
    def __init__(self):
        self._symbol_counts = defaultdict(int)

    def previsit(self, node):
        if isinstance(node, (Class, Rule)) and node.params:
            for param in node.params:
                self._symbol_counts[param] += 1
        elif isinstance(node, LetExpression):
            # Ideally, the binding would only apply to the body of the let-expression.
            # But this is probably fine for now.
            self._symbol_counts[node.name] += 1

    def postvisit(self, node):
        if isinstance(node, (Class, Rule)) and node.params:
            for param in node.params:
                self._symbol_counts[param] -= 1
        elif isinstance(node, LetExpression):
            self._symbol_counts[node.name] -= 1

    def is_bound(self, ref):
        return self._symbol_counts[ref.name] > 0


def _update_local_references(rules):
    counter = _SymbolCounter()
    def previsit(node):
        counter.previsit(node)
        if isinstance(node, Ref) and counter.is_bound(node):
            node.is_local = True

    visit(previsit, rules, counter.postvisit)


def _update_rule_references(rules):
    rule_names = set()
    for rule in rules:
        if isinstance(rule, (Class, Rule)):
            rule_names.add(rule.name)

    def check_refs(node):
        if isinstance(node, Ref) and node.name in rule_names and not node.is_local:
            node.name = _cont_name(node.name)

    visit(check_refs, rules)


def _freevars(expr):
    result = set()
    counter = _SymbolCounter()

    def previsit(node):
        counter.previsit(node)
        if isinstance(node, Ref) and not counter.is_bound(node) and node.is_local:
            result.add(node.name)

    visit(previsit, expr, counter.postvisit)
    return result


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


class Rule:
    def __init__(self, name, parse):
        self.name = name
        self.parse = parse

    def __repr__(self):
        return f'Rule(name={self.name!r}, parse={self.parse.__name__})'
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


class _ParseFunction(_nt('_ParseFunction', 'func, args, kwargs')):
    def __call__(self, _text, _pos):
        return self.func(_text, _pos, *self.args, **dict(self.kwargs))


class _StringLiteral(str):
    def __call__(self, _text, _pos):
        return self._parse_function(_text, _pos)


def _wrap_string_literal(string_value, parse_function):
    result = _StringLiteral(string_value)
    result._parse_function = parse_function
    return result


def _run(text, pos, start):
    memo = {}
    result = None

    key = ($CALL, start, pos)
    gtor = start(text, pos)
    stack = [(key, gtor)]

    while stack:
        key, gtor = stack[-1]
        result = gtor.send(result)

        if result[0] != $CALL:
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
