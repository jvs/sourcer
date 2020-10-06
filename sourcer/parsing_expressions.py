from collections import defaultdict
from contextlib import contextmanager
import typing
from string import Template

from .program_builder import (
    Binop, LIST, ProgramBuilder, Raise, Raw, Return, Tup, Val, Var, Yield,
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

CALL = 3


class Expr:
    def always_succeeds(self):
        return False

    def compile(self, pb):
        if pb.has_available_blocks(self.num_blocks):
            self._compile(pb)
        else:
            func, params = _functionalize(pb, self, is_generator=False)
            pb(Tup(STATUS, RESULT, POS) << func(*params))


def _add_comment(pb, expr):
    content = str(expr)

    if '\n' not in content:
        pb(Raw('# ' + content))
        return

    pb(
        Raw('"""'),
        *[Raw(x) for x in content.replace('"""', '\\"\\"\\"').split('\n')],
        Raw('"""'),
    )


def _functionalize(pb, expr, is_generator=False):
    name = f'_parse_function_{expr.program_id}'
    params = [str(TEXT), str(POS)] + list(sorted(_freevars(expr)))
    with pb.global_function(name, params):
        expr._compile(pb)
        cls = Yield if is_generator else Return
        pb(cls(Tup(STATUS, RESULT, POS)))
    return Raw(name), [Raw(x) for x in params]


@contextmanager
def _if_succeeds(pb, expr):
    expr.compile(pb)
    if expr.always_succeeds():
        yield
    else:
        with pb.IF(STATUS):
            yield


@contextmanager
def _if_fails(pb, expr):
    expr.compile(pb)
    if expr.always_succeeds():
        with pb._sandbox():
            yield
    else:
        with pb.IF_NOT(STATUS):
            yield


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

    def __str__(self):
        op = '/' if self.allow_trailer else '//'
        wrap = lambda x: f'({x})' if isinstance(x, BinaryOp) else x
        return f'{wrap(self.expr)} {op} {wrap(self.separator)}'

    def always_succeeds(self):
        return self.allow_empty

    def _compile(self, pb):
        pb(Raw(f'# <{self.__class__.__name__}>'))
        _add_comment(pb, self)
        staging = pb.var('staging', Raw('[]'))
        checkpoint = pb.var('checkpoint', POS)

        with pb.loop():
            with _if_fails(pb, self.expr):
                pb(BREAK)

            pb(staging.append(RESULT))
            pb(checkpoint << POS)

            with _if_fails(pb, self.separator):
                pb(BREAK)

            if self.allow_trailer:
                pb(checkpoint << POS)

        success = [RESULT << staging, STATUS << True, POS << checkpoint]

        if self.allow_empty:
            pb(*success)
        else:
            with pb.IF(staging):
                pb(*success)
        pb(Raw(f'# </{self.__class__.__name__}>'))


class Apply(Expr):
    num_blocks = 2

    def __init__(self, expr1, expr2, apply_left=False):
        self.expr1 = expr1
        self.expr2 = expr2
        self.apply_left = apply_left

    def __str__(self):
        op = '<|' if self.apply_left else '|>'
        wrap = lambda x: f'({x})' if isinstance(x, BinaryOp) else x
        return f'{wrap(self.expr1)} {op} {wrap(self.expr2)}'

    def always_succeeds(self):
        return self.expr1.always_succeeds() and self.expr2.always_succeeds()

    def _compile(self, pb):
        pb(Raw(f'# <{self.__class__.__name__}>'))
        _add_comment(pb, self)

        with _if_succeeds(pb, self.expr1):
            first = pb.var('func' if self.apply_left else 'arg', RESULT)
            with _if_succeeds(pb, self.expr2):
                result = first(RESULT) if self.apply_left else RESULT(first)
                pb(RESULT << result)
        pb(Raw(f'# </{self.__class__.__name__}>'))


class Call(Expr):
    num_blocks = 0

    def __init__(self, func, args):
        self.func = func
        self.args = args

    def __str__(self):
        args = ', '.join(str(x) for x in self.args)
        return f'{self.func}({args})'

    def _compile(self, pb):
        pb(Raw(f'# <{self.__class__.__name__}>'))
        _add_comment(pb, self)
        args, kwargs = [], []

        for arg in self.args:
            is_kw = isinstance(arg, KeywordArg)
            expr = arg.expr if is_kw else arg

            if isinstance(expr, Ref):
                value = Raw(expr.resolved)
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
                kwargs.append(Tup(Val(arg.name), value))
            else:
                args.append(value)

        func = raw._ParseFunction(Raw(self.func.resolved), Tup(*args), Tup(*kwargs))
        func = pb.var('func', func)
        pb(Tup(STATUS, RESULT, POS) << Yield(Tup(CALL, func, POS)))
        pb(Raw(f'# </{self.__class__.__name__}>'))


class Choice(Expr):
    num_blocks = 2

    def __init__(self, *exprs):
        self.exprs = exprs

    def __str__(self):
        return ' | '.join(str(x) for x in self.exprs)

    def always_succeeds(self):
        return any(x.always_succeeds() for x in self.exprs)

    def _compile(self, pb):
        pb(Raw(f'# <{self.__class__.__name__}>'))
        backtrack = Var('backtrack')
        farthest_pos = Var('farthest_pos')

        pb(backtrack << farthest_pos << POS)

        farthest_err = pb.var('farthest_err', Val(self.program_id))
        farthest_err = pb.var('farthest_err', Raw(_error_func_name(self)))

        with pb.breakable():
            for i, expr in enumerate(self.exprs):
                pb(Raw(f'# Option {i+1}:'))

                with _if_succeeds(pb, expr):
                    pb(BREAK)

                with pb.IF(farthest_pos < POS):
                    pb(farthest_pos << POS)
                    pb(farthest_err << RESULT)

                if i + 1 < len(self.exprs):
                    pb(POS << backtrack)

            pb(POS << farthest_pos)
            pb(RESULT << farthest_err)
        pb(Raw(f'# </{self.__class__.__name__}>'))

    def complain(self):
        return 'Unexpected input'


class Class(Expr):
    num_blocks = 2

    def __init__(self, name, params, fields, is_ignored=False):
        self.name = name
        self.params = params
        self.fields = fields
        self.is_ignored = is_ignored
        self.extra_id = None

    def __str__(self):
        params = '' if self.params is None else f'({", ".join(self.params)})'
        fields = ''.join(f'    {x.name}: {x.expr}\n' for x in self.fields)
        return f'class {self.name}{params} {{\n{fields}}}'

    def always_succeeds(self):
        return all(x.expr.always_succeeds() for x in self.fields)

    def _compile(self, pb):
        field_names = [x.name for x in self.fields]
        parse_func = Raw(f'{_cont_name(self.name)}')

        with pb.global_class(self.name, 'Node'):
            _add_comment(pb, self)
            pb(raw._fields << Tup(*[Val(x) for x in field_names]))

            with pb.local_function('__init__', ['self'] + field_names):
                for name in field_names:
                    pb(Raw(f'self.{name} = {name}'))
                pb(Raw('self._position_info = None'))

            with pb.local_function('__repr__', ['self']):
                values = ', '.join(f'{x}={{self.{x}!r}}' for x in field_names)
                pb(Return(Raw(f"f'{self.name}({values})'")))

            pb(Raw('@staticmethod'))
            if self.params:
                with pb.local_function('parse', self.params):
                    args = Tup(*self.params)
                    kwargs = Raw('{}')
                    pb(raw.closure << raw._ParseFunction(parse_func, args, kwargs))
                    pb(Return(Raw(
                        'lambda text, pos=0, fullparse=True:'
                        ' _run(text, pos, closure, fullparse)'
                    )))
            else:
                with pb.local_function('parse', ['text', 'pos=0', 'fullparse=True']):
                    pb(Return(Raw(f'_run(text, pos, {parse_func}, fullparse)')))

        params = [str(TEXT), str(POS)] + (self.params or [])
        with pb.global_function(parse_func, params):
            exprs = (x.expr for x in self.fields)
            seq = Seq(*exprs, names=field_names, constructor=self.name)
            seq.program_id = self.extra_id
            seq.compile(pb)
            pb(Yield(Tup(STATUS, RESULT, POS)))


class Discard(Expr):
    num_blocks = 2

    def __init__(self, expr1, expr2, discard_left=True):
        self.expr1 = expr1
        self.expr2 = expr2
        self.discard_left = discard_left

    def __str__(self):
        op = '>>' if self.discard_left else '<<'
        wrap = lambda x: f'({x})' if isinstance(x, BinaryOp) else x
        return f'{wrap(self.expr1)} {op} {wrap(self.expr2)}'

    def always_succeeds(self):
        return (self.expr1.always_succeeds()
            and self.expr2.always_succeeds())

    def _compile(self, pb):
        pb(Raw(f'# <{self.__class__.__name__}>'))
        _add_comment(pb, self)

        with pb.breakable():
            with _if_fails(pb, self.expr1):
                pb(BREAK)

            if self.discard_left:
                self.expr2.compile(pb)
            else:
                staging = pb.var('staging', RESULT)
                with _if_succeeds(pb, self.expr2):
                    pb(RESULT << staging)

        pb(Raw(f'# </{self.__class__.__name__}>'))


class Expect(Expr):
    num_blocks = 0

    def __init__(self, expr):
        self.expr = expr

    def __str__(self):
        return f'Expect({self.expr})'

    def always_succeeds(self):
        return self.expr.always_succeeds()

    def _compile(self, pb):
        pb(Raw(f'# <{self.__class__.__name__}>'))
        _add_comment(pb, self)
        backtrack = pb.var('backtrack', POS)

        with _if_succeeds(pb, self.expr):
            pb(POS << backtrack)

        pb(Raw(f'# </{self.__class__.__name__}>'))


class ExpectNot(Expr):
    num_blocks = 1

    def __init__(self, expr):
        self.expr = expr

    def __str__(self):
        return f'ExpectNot({self.expr})'

    def _compile(self, pb):
        pb(Raw(f'# <{self.__class__.__name__}>'))
        _add_comment(pb, self)

        backtrack = pb.var('backtrack', POS)
        self.expr.compile(pb)
        pb(POS << backtrack)

        with pb.IF(STATUS):
            pb(STATUS << Val(False))
            pb(RESULT << Raw(_error_func_name(self)))

        with pb.ELSE():
            pb(STATUS << Val(True))
            pb(RESULT << Val(None))
        pb(Raw(f'# </{self.__class__.__name__}>'))

    def complain(self):
        return f'Did not expect to match: {self.expr}'


class Fail(Expr):
    num_blocks = 0

    def __init__(self, message=None):
        self.message = message

    def __str__(self):
        return 'Fail()' if self.message is None else f'Fail({self.message!r})'

    def _compile(self, pb):
        pb(Raw(f'# <{self.__class__.__name__}>'))
        _add_comment(pb, self)
        pb(STATUS << False, RESULT << Raw(_error_func_name(self)))
        pb(Raw(f'# </{self.__class__.__name__}>'))

    def complain(self):
        return 'Failed' if self.message is None else str(self.message)


class KeywordArg:
    def __init__(self, name, expr):
        self.name = name
        self.expr = expr

    def __str__(self):
        return f'{self.name}={self.expr}'


def Left(expr1, expr2):
    return Discard(expr1, expr2, discard_left=False)


class LetExpression(Expr):
    num_blocks = 1

    def __init__(self, name, expr, body):
        self.name = name
        self.expr = expr
        self.body = body

    def __str__(self):
        return f'let {self.name} = {self.expr} in\n{self.body}'

    def always_succeeds(self):
        return (self.expr.always_succeeds()
            and self.body.always_succeeds())

    def _compile(self, pb):
        pb(Raw('# <Let>'))
        _add_comment(pb, self)

        with _if_succeeds(pb, self.expr):
            pb(Raw(self.name) << RESULT)
            self.body.compile(pb)

        pb(Raw('# </Let>'))


class List(Expr):
    num_blocks = 2

    def __init__(self, expr, allow_empty=True):
        self.expr = expr
        self.allow_empty = allow_empty

    def __str__(self):
        x = f'({self.expr})' if isinstance(self.expr, BinaryOp) else self.expr
        op = '*' if self.allow_empty else '+'
        return f'{x}{op}'

    def always_succeeds(self):
        return self.allow_empty

    def _compile(self, pb):
        pb(Raw(f'# <{self.__class__.__name__}>'))
        _add_comment(pb, self)
        staging = pb.var('staging', Raw('[]'))

        with pb.loop():
            checkpoint = pb.var('checkpoint', POS)

            with _if_fails(pb, self.expr):
                pb(POS << checkpoint, BREAK)

            pb(staging.append(RESULT))

        success = [
            RESULT << staging,
            STATUS << True,
        ]

        if self.allow_empty:
            pb(*success)
        else:
            with pb.IF(staging):
                pb(*success)

        pb(Raw(f'# </{self.__class__.__name__}>'))


class Opt(Expr):
    num_blocks = 1

    def __init__(self, expr):
        self.expr = expr

    def __str__(self):
        return f'Opt({self.expr})'

    def always_succeeds(self):
        return True

    def _compile(self, pb):
        pb(Raw(f'# <{self.__class__.__name__}>'))
        _add_comment(pb, self)
        backtrack = pb.var('backtrack', POS)

        with _if_fails(pb, self.expr):
            pb(
                STATUS << Val(True),
                POS << backtrack,
                RESULT << Val(None),
            )
        pb(Raw(f'# </{self.__class__.__name__}>'))


class Ref(Expr):
    num_blocks = 0

    def __init__(self, name):
        self.name = name
        self.is_local = False
        self._resolved = None

    @property
    def resolved(self):
        return self.name if self._resolved is None else self._resolved

    def __str__(self):
        return self.name

    def _compile(self, pb):
        pb(Raw(f'# <{self.__class__.__name__} name={self.name!r}>'))
        func = self.name if self._resolved is None else self._resolved
        pb(Tup(STATUS, RESULT, POS) << Yield(Tup(CALL, Raw(func), POS)))
        pb(Raw(f'# </{self.__class__.__name__}>'))


class RegexLiteral(Expr):
    num_blocks = 1

    def __init__(self, pattern):
        if isinstance(pattern, typing.Pattern):
            pattern = pattern.pattern
        if not isinstance(pattern, str):
            raise TypeError('Expected str')
        self.pattern = pattern
        self.skip_ignored = False

    def __str__(self):
        pattern = self.pattern.replace('\\', '\\\\')
        return f'@/{pattern}/'

    def _compile(self, pb):
        pb(Raw(f'# <Regex pattern={self.pattern!r}>'))
        matcher = pb.define_global('matcher', f'_compile_re({self.pattern!r}).match')
        match = pb.var('match', matcher(TEXT, POS))
        end = match.end()

        with pb.IF(match):
            pb(
                POS << (_skip_ignored(end) if self.skip_ignored else end),
                STATUS << True,
                RESULT << match.group(0),
            )

        with pb.ELSE():
            pb(STATUS << False, RESULT << Raw(_error_func_name(self)))

        pb(Raw('# </Regex>'))

    def complain(self):
        return f'Expected to match the regular expression /{self.pattern}/'


def Right(expr1, expr2):
    return Discard(expr1, expr2, discard_left=True)


class Rule(Expr):
    num_blocks = 1

    def __init__(self, name, params, expr, is_ignored=False):
        self.name = name
        self.params = params
        self.expr = expr
        self.is_ignored = is_ignored

    def __str__(self):
        params = '' if self.params is None else f'({", ".join(self.params)})'
        return f'{self.name}{params} = {self.expr}'

    def _compile(self, pb):
        params = [str(TEXT), str(POS)] + (self.params or [])
        cont_name = _cont_name(self.name)
        entry_name = _entry_name(self.name)

        with pb.global_function(cont_name, params):
            pb(Raw(f'# Rule {self.name!r}'))
            self.expr.compile(pb)
            pb(Yield(Tup(STATUS, RESULT, POS)))

        with pb.global_function(entry_name, ['text', 'pos=0', 'fullparse=True']):
            pb(Return(Raw(f'_run(text, pos, {cont_name}, fullparse)')))

        with pb.global_section():
            definition = str(self)
            if '"""' in definition:
                definition = definition.replace('"""', '"\\""')
            pb(
                Raw(f'{self.name} = Rule({self.name!r}, {entry_name}, """'),
                *[Raw(f'    {x}') for x in definition.split('\n')],
                Raw('""")'),
            )


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
        self.needs_parse_info = constructor is not None

    def __str__(self):
        return f'[{", ".join(str(x) for x in self.exprs)}]'

    def _compile(self, pb):
        pb(Raw(f'# <{self.__class__.__name__}>'))

        if self.needs_parse_info:
            start_pos = pb.var('start_pos', POS)

        with pb.breakable():
            items = []
            for name, expr in zip(self.names, self.exprs):

                with _if_fails(pb, expr):
                    pb(BREAK)

                item = Var('item') if name is None else Raw(name)
                pb(item << RESULT)
                items.append(item)

            ctor = LIST if self.constructor is None else Raw(self.constructor)
            pb(RESULT << ctor(*items))

            if self.needs_parse_info:
                pb(RESULT._position_info << Tup(start_pos, POS))

        pb(Raw(f'# </{self.__class__.__name__}>'))


class Skip(Expr):
    num_blocks = 2

    def __init__(self, *exprs):
        self.exprs = exprs

    def __str__(self):
        return f'Skip({", ".join(str(x) for x in self.exprs)})'

    def always_succeeds(self):
        return True

    def _compile(self, pb):
        pb(Raw(f'# <{self.__class__.__name__}>'))
        _add_comment(pb, self)
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
        pb(Raw(f'# </{self.__class__.__name__}>'))


def Some(expr):
    return List(expr, allow_empty=False)


class StringLiteral(Expr):
    def __init__(self, value):
        if not isinstance(value, str):
            raise TypeError(f'Expected str. Received: {type(value)}.')
        self.value = value
        self.skip_ignored = False
        self.num_blocks = 0 if self.value == '' else 1

    def __str__(self):
        return repr(self.value)

    def always_succeeds(self):
        return self.value == ''

    def _compile(self, pb):
        pb(Raw(f'# <String value={self.value!r}>'))
        if self.value == '':
            pb(STATUS << Val(True), RESULT << Val(''))
            pb(Raw('# </String>'))
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
            pb(STATUS << False, RESULT << Raw(_error_func_name(self)))

        pb(Raw('# </String>'))

    def complain(self):
        return f'Expected to match the string {self.value!r}'


class OperatorPrecedence(Expr):
    def __init__(self, atom, *rules):
        self.atom = atom
        self.rules = rules
        self.num_blocks = (rules[-1] if rules else atom).num_blocks

    def __str__(self):
        rules = [self.atom] + list(self.rules)
        lines = ',\n'.join(f'    {x}' for x in rules)
        return f'OperatorPrecedence(\n{lines}\n)'

    def _compile(self, pb):
        pb(Raw(f'# <{self.__class__.__name__}>'))
        _add_comment(pb, self)
        prev = self.atom
        for rule in self.rules:
            rule.operand = prev
            prev = rule
        prev.compile(pb)
        pb(Raw(f'# </{self.__class__.__name__}>'))


class OperatorPrecedenceRule(Expr):
    def __init__(self, *operators):
        self.operators = operators[0] if len(operators) == 1 else Choice(*operators)
        self.operand = None

    def __str__(self):
        return f'{self.__class__.__name__}({self.operators})'


class LeftAssoc(OperatorPrecedenceRule):
    num_blocks = 2

    def _compile(self, pb):
        pb(Raw(f'# <{self.__class__.__name__}>'))
        _add_comment(pb, self)
        is_first = pb.var('is_first', Val(True))
        staging = pb.var('staging', Val(None))
        operator = Var('operator')

        with pb.loop():
            with _if_fails(pb, self.operand):
                pb(BREAK)

            checkpoint = pb.var('checkpoint', POS)

            with pb.IF(is_first):
                pb(is_first << Val(False))
                pb(staging << RESULT)

            with pb.ELSE():
                pb(staging << raw.Infix(staging, operator, RESULT))
                if isinstance(self, NonAssoc):
                    pb(BREAK)

            with _if_fails(pb, self.operators):
                pb(BREAK)

            pb(operator << RESULT)

        with pb.IF_NOT(is_first):
            pb(
                STATUS << Val(True),
                RESULT << staging,
                POS << checkpoint,
            )
        pb(Raw(f'# </{self.__class__.__name__}>'))


class NonAssoc(LeftAssoc):
    pass

class RightAssoc(OperatorPrecedenceRule):
    num_blocks = 4

    def _compile(self, pb):
        pb(Raw(f'# <{self.__class__.__name__}>'))
        _add_comment(pb, self)
        backup = pb.var('backup', Val(None))
        prev = pb.var('prev', Val(None))

        staging = Var('staging')
        checkpoint = Var('checkpoint')

        with pb.loop():

            with _if_fails(pb, self.operand):
                with pb.IF(prev):
                    with pb.IF(backup):
                        pb(backup.right << prev.left, RESULT << staging)
                    with pb.ELSE():
                        pb(RESULT << prev.left)
                    pb(STATUS << Val(True), POS << checkpoint)
                pb(BREAK)

            pb(checkpoint << POS)
            operand = pb.var('operand', RESULT)

            with _if_fails(pb, self.operators):
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

        pb(Raw(f'# </{self.__class__.__name__}>'))


class Postfix(OperatorPrecedenceRule):
    num_blocks = 3

    def _compile(self, pb):
        pb(Raw(f'# <{self.__class__.__name__}>'))
        _add_comment(pb, self)

        with _if_succeeds(pb, self.operand):
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
        pb(Raw(f'# </{self.__class__.__name__}>'))


class Prefix(OperatorPrecedenceRule):
    num_blocks = 2

    def _compile(self, pb):
        pb(Raw(f'# <{self.__class__.__name__}>'))
        _add_comment(pb, self)
        prev = pb.var('prev', Val(None))
        checkpoint = pb.var('checkpoint', POS)
        staging = Var('staging')

        with pb.loop():

            with _if_fails(pb, self.operators):
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
        pb(Raw(f'# </{self.__class__.__name__}>'))


class PythonExpression(Expr):
    num_blocks = 0

    def __init__(self, source_code):
        self.source_code = source_code

    def __str__(self):
        return f'`{self.source_code}`'

    def always_succeeds(self):
        return True

    def _compile(self, pb):
        pb(RESULT << Raw(self.source_code), STATUS << True)


class PythonSection:
    def __init__(self, source_code):
        self.source_code = source_code

    def __str__(self):
        return f'```{self.source_code}```'


class Where(Expr):
    num_blocks = 2

    def __init__(self, expr, predicate):
        self.expr = expr
        self.predicate = predicate

    def __str__(self):
        wrap = lambda x: f'({x})' if isinstance(x, BinaryOp) else x
        return f'{wrap(self.expr)} where {wrap(self.predicate)}'

    def _compile(self, pb):
        pb(Raw(f'# <{self.__class__.__name__}>'))
        _add_comment(pb, self)

        with _if_succeeds(pb, self.expr):
            arg = pb.var('arg', RESULT)

            with _if_succeeds(pb, self.predicate):
                with pb.IF(RESULT(arg)):
                    pb(RESULT << arg)

                with pb.ELSE():
                    pb(STATUS << False)
                    pb(RESULT << Raw(_error_func_name(self)))
        pb(Raw(f'# </{self.__class__.__name__}>'))

    def complain(self):
        return f'Expected to satisfy the predicate: {self.predicate}'


def _skip_ignored(pos):
    return Yield(Tup(CALL, Raw(_cont_name('_ignored')), pos))[2]


def _cont_name(name):
    return f'_cont_{name}'


def _entry_name(name):
    return f'_parse_{name}'


def _error_func_name(expr):
    return f'_raise_error{expr.program_id}'


BinaryOp = (Alt, Apply, Choice, Discard, Where)


def generate_source_code(docstring, nodes):
    pb = ProgramBuilder(docstring=docstring)
    pb.add_import('from collections import namedtuple as _nt')
    pb.add_import('from re import compile as _compile_re')
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
        rules.append(Rule('_ignored', None, Skip(*refs), 'ignored'))

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

    visited = set()
    def maybe_compile_error_message(rule, expr):
        if not hasattr(expr, 'complain') or expr.program_id in visited:
            return

        visited.add(expr.program_id)
        if expr.always_succeeds():
            return

        with pb.global_function(_error_func_name(expr), [str(TEXT), str(POS)]):
            with pb.IF(raw.len(TEXT) <= POS):
                pb(
                    raw.title << Val('Unexpected end of input.'),
                    raw.line << Val(None),
                    raw.col << Val(None),
                )

            with pb.ELSE():
                pb(
                    Tup(raw.line, raw.col) << raw._get_line_and_column(TEXT, POS),
                    raw.excerpt << raw._extract_excerpt(TEXT, POS, raw.col),
                    raw.title << Raw(
                        r"f'Error on line {line}, column {col}:\n{excerpt}\n'"
                    ),
                )

            pb(
                raw.details << Raw('('),
                Val(f'Failed to parse the {rule.name!r} rule, at the expression:\n'),
                Val(f'    {str(expr)}\n\n'),
                Val(expr.complain()),
                Raw(')'),
                Raise(raw.ParseError(raw.title + raw.details, POS, raw.line, raw.col)),
            )

    for rule in rules:
        rule.compile(pb)
        visit(lambda x: maybe_compile_error_message(rule, x), rule)

    return pb.generate_source_code()


def _assign_ids(rules):
    next_id = 1
    def assign_id(node):
        nonlocal next_id
        node.program_id = next_id
        next_id += 1
        if isinstance(node, Class):
            node.extra_id = next_id
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
            node._resolved = _cont_name(node.name)

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
    def __init__(self, name, parse, definition):
        self.name = name
        self.parse = parse
        self.definition = definition

    def __repr__(self):
        return (f'Rule(name={self.name!r}, parse={self.parse.__name__},'
            f' definition={self.definition!r})')
'''


_main_template = r'''
class ParseError(Exception):
    def __init__(self, message, index, line, column):
        super().__init__(message)
        self.position = _Position(index, line, column)


class PartialParseError(Exception):
    def __init__(self, partial_result, last_position, excerpt):
        super().__init__('Incomplete parse. Unexpected input on line'
            f' {last_position.line}, column {last_position.column}:\n{excerpt}')
        self.partial_result = partial_result
        self.last_position = last_position


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


def parse(text, pos=0, fullparse=True):
    return _run(text, pos, $start, fullparse)


_PositionInfo = _nt('_PositionInfo', 'start, end')

_Position = _nt('_Position', 'index, line, column')


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


def _run(text, pos, start, fullparse):
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
        return _finalize_parse_info(text, result[1], result[2], fullparse)
    else:
        pos = result[2]
        message = result[1](text, pos)
        raise ParseError(message, pos)


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


def _finalize_parse_info(text, nodes, pos, fullparse):
    line_numbers, column_numbers = _map_index_to_line_and_column(text)

    for node in visit(nodes):
        parse_info = getattr(node, '_position_info', None)
        if parse_info:
            start, end = parse_info
            end -= 1
            node._position_info = _PositionInfo(
                start=_Position(start, line_numbers[start], column_numbers[start]),
                end=_Position(end, line_numbers[end], column_numbers[end]),
            )

    if fullparse and pos < len(text):
        line, col = line_numbers[pos], column_numbers[pos]
        position = _Position(pos, line, col)
        excerpt = _extract_excerpt(text, pos, col)
        raise PartialParseError(nodes, position, excerpt)

    return nodes


def _extract_excerpt(text, pos, col):
    start = pos - (col - 1)
    match = _compile_re('\n').search(text, pos + 1)
    end = len(text) if match is None else match.start()

    if end - start < 96:
        return text[start : end] + _caret_at(col - 1)

    if col < 60:
        # Chop the line off at the end.
        return text[start : start + 90] + ' ...' + _caret_at(col - 1)

    elif end - pos < 40:
        # Chop the line off at the start.
        return '... ' + text[end - 90 : end] + _caret_at(pos - (end - 90) + 4)

    else:
        # Chop the line off at both ends.
        return '... ' + text[pos - 42 : pos + 42] + ' ...' + _caret_at(42 + 4)


def _caret_at(index):
    return '\n' + (' ' * index) + '^'


def _get_line_and_column(text, pos):
    line_numbers, column_numbers = _map_index_to_line_and_column(text)
    return line_numbers[pos], column_numbers[pos]


def _map_index_to_line_and_column(text):
    line_numbers = []
    column_numbers = []

    current_line = 1
    current_column = 0

    for c in text:
        if c == '\n':
            current_line += 1
            current_column = 0
        else:
            current_column += 1
        line_numbers.append(current_line)
        column_numbers.append(current_column)

    return line_numbers, column_numbers
'''
