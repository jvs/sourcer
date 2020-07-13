import typing


class Alt:
    def __init__(self, expr, separator, allow_trailer=False, allow_empty=True):
        self.expr = expr
        self.separator = separator
        self.allow_trailer = allow_trailer
        self.allow_empty = allow_empty

    def _eval(self, env):
        return Alt(
            expr=self.expr._eval(env),
            separator=self.separator._eval(env),
            allow_trailer=self.allow_trailer,
            allow_empty=self.allow_empty,
        )

    def _compile(self, out):
        staging = out.define('staging', '[]')
        checkpoint = out.define('checkpoint', '_pos')

        loop = out.reserve('loop_alt')
        end = out.reserve('end_alt')

        out.label(loop)
        out.compile(self.expr)

        with out.IF_NOT('_mode'):
            out.goto(end)

        out(f'{staging}.append(_result)')
        out.set(checkpoint, '_pos')

        out.compile(self.separator)

        with out.IF_NOT('_mode'):
            out.goto(end)

        if self.allow_trailer:
            out.set(checkpoint, '_pos')

        out.goto(loop)
        out.label(end)

        if not self.allow_empty:
            out(f'if {staging}:')
            out.indent += 1

        out.set('_mode', True)
        out.set('_result', staging)
        out.set('_pos', checkpoint)


class Apply:
    def __init__(self, expr1, expr2, apply_left=False):
        self.expr1 = expr1
        self.expr2 = expr2
        self.apply_left = apply_left

    def _eval(self, env):
        return Apply(
            expr1=self.expr1._eval(env),
            expr2=self.expr2._eval(env),
            apply_left=self.apply_left,
        )

    def _compile(self, out):
        out.compile(self.expr1)
        end = out.reserve('end_apply')

        with out.IF_NOT('_mode'):
            out.goto(end)

        first = out.define('_item', '_result')
        out.compile(self.expr2)
        func, arg = (first, '_result') if self.apply_left else ('_result', first)

        with out.IF('_mode'):
            out.set('_result', f'{func}({arg})')

        out.label(end)


class Call:
    def __init__(self, func, args):
        self.func = func
        self.args = args

    def _eval(self, env):
        func = self.func._eval(env)
        if callable(func):
            a = [x._eval(env) for x in self.args if not isinstance(x, KeywordArg)]
            k = {x.name: x._eval(env) for x in self.args if isinstance(x, KeywordArg)}
            return func(*a, **k)
        else:
            raise Exception(f'Not callable: {func!r}')


class Choice:
    def __init__(self, *exprs):
        self.exprs = exprs

    def _eval(self, env):
        return Choice(*[x._eval(env) for x in self.exprs])

    def _compile(self, out):
        backtrack = out.define('backtrack', '_pos')
        farthest_pos = out.define('farthest_pos', '_pos')
        farthest_expr = out.define('farthest_expr', id(self))

        end = out.reserve('end_choice')
        for expr in self.exprs:
            out.compile(expr)
            with out.IF('_mode'):
                out.goto(end)
            with out.IF(f'{farthest_pos} < _pos'):
                out.set(farthest_pos, '_pos')
                out.set(farthest_expr, id(expr))
            out.set('_pos', backtrack)

        out.set('_result', farthest_expr)
        out.set('_pos', farthest_pos)
        out.label(end)


class Class:
    def __init__(self, name, fields, is_ignored=False):
        self.name = name
        self.fields = fields
        self.is_ignored = is_ignored

    def _replace(self, **kw):
        for field in ['name', 'fields', 'is_ignored']:
            if field not in kw:
                kw[field] = getattr(self, field)
        return Class(**kw)

    def _eval(self, env):
        return self._replace(fields=[x._eval(env) for x in self.fields])

    def _compile(self, out):
        write = out.global_defs.write
        write(f'\nclass {self.name}(Node):\n')

        names = tuple(x.name for x in self.fields)
        write(f'    _fields = {names!r}\n\n')

        params = ', '.join(x.name for x in self.fields)
        write(f'    def __init__(self, {params}):\n')
        for field in self.fields:
            write(f'        self.{field.name} = {field.name}\n')
        write('\n')

        write(f'    def __repr__(self):\n')
        inits = ', '.join(f'{x.name}={{self.{x.name}!r}}' for x in self.fields)
        write(f'        return f\'{self.name}({inits})\'\n\n')

        exprs = (x.expr for x in self.fields)
        return out.compile(Seq(*exprs, constructor=self.name))


class Discard:
    def __init__(self, expr1, expr2, discard_left=True):
        self.expr1 = expr1
        self.expr2 = expr2
        self.discard_left = discard_left

    def _eval(self, env):
        return Discard(
            expr1=self.expr1._eval(env),
            expr2=self.expr2._eval(env),
            discard_left=self.discard_left,
        )

    def _compile(self, out):
        out.compile(self.expr1)
        end = out.reserve('end_discard')

        with out.IF_NOT('_mode'):
            out.goto(end)

        if self.discard_left:
            out.compile(self.expr2)
        else:
            staging = out.define('staging', '_result')
            out.compile(self.expr2)
            with out.IF('_mode'):
                out.set('_result', staging)

        out.label(end)


class Expect:
    def __init__(self, expr):
        self.expr = expr

    def _eval(self, env):
        return Expect(self.expr._eval(env))

    def _compile(self, out):
        backtrack = out.define('backtrack', '_pos')
        out.compile(self.expr)
        out.set('_pos', backtrack)


class ExpectNot:
    def __init__(self, expr):
        self.expr = expr

    def _eval(self, env):
        return ExpectNot(self.expr._eval(env))

    def _compile(self, out):
        backtrack = out.define('backtrack', '_pos')
        out.compile(self.expr)
        out.set('_pos', backtrack)
        with out.IF('_mode'):
            out.set('_mode', False)
            out.set('_result', id(self))
        with out.ELSE():
            out.set('_mode', True)
            out.set('_result', None)


class Fail:
    def __init__(self, message):
        self.message = None

    def _eval(self, env):
        return self

    def _compile(self, out):
        out.set('_mode', False)
        out.set('_result', id(self))


class KeywordArg:
    def __init__(self, name, expr):
        self.name = name
        self.expr = expr

    def _eval(self, env):
        return KeywordArg(self.name, self.expr._eval(env))


def Left(expr1, expr2):
    return Discard(expr1, expr2, discard_left=False)


class List:
    def __init__(self, expr, allow_empty=True):
        self.expr = expr
        self.allow_empty = allow_empty

    def _eval(self, env):
        return List(expr=self.expr._eval(env), allow_empty=self.allow_empty)

    def _compile(self, out):
        staging = out.define('staging', '[]')
        loop = out.reserve('loop_list')
        end = out.reserve('end_list')

        out.label(loop)
        checkpoint = out.define('checkpoint', '_pos')
        out.compile(self.expr)

        with out.IF('_mode'):
            out(f'{staging}.append(_result)')
            out.goto(loop)

        with out.ELSE():
            out.set('_pos', checkpoint)
            out.goto(end)

        out.label(end)

        if not self.allow_empty:
            out(f'if {staging}:')
            out.indent += 1

        out.set('_mode', True)
        out.set('_result', staging)


class Opt:
    def __init__(self, expr):
        self.expr = expr

    def _eval(self, env):
        return Opt(self.expr._eval(env))

    def _compile(self, out):
        backtrack = out.define('backtrack', '_pos')
        out.compile(self.expr)
        with out.IF_NOT('_mode'):
            out.set('_mode', True)
            out.set('_result', None)
            out.set('_pos', backtrack)


class Pass:
    def __init__(self, value):
        self.value = value

    def _eval(self, env):
        return self

    def _compile(self, out):
        out.set('_mode', True)
        out.set('_result', repr(self.value))


class Ref:
    def __init__(self, name):
        self.name = name

    def _eval(self, env):
        return env.get(self.name, self)

    def _compile(self, out):
        rule = out.rule_map[self.name]
        out(f'_mode, _result, _pos = yield ({out.CONTINUE}, {rule}, _pos)')


class RegexLiteral:
    def __init__(self, pattern):
        if isinstance(pattern, typing.Pattern):
            pattern = pattern.pattern
        if not isinstance(pattern, str):
            raise TypeError('Expected str')
        self.pattern = pattern

    def _eval(self, env):
        return self

    def _compile(self, out):
        out.add_import('re')
        pattern = out.define_constant('pattern', f're.compile({self.pattern!r})')
        match = out.define('match', f'{pattern}.match(_text, _pos)')

        with out.IF(match):
            out.set('_pos', f'{match}.end()')
            out.skip_ignored()
            out.set('_mode', True)
            out.set('_result', f'{match}.group(0)')

        with out.ELSE():
            out.set('_mode', False)
            out.set('_result', id(self))


def Right(expr1, expr2):
    return Discard(expr1, expr2, discard_left=True)


class Rule:
    def __init__(self, name, expr, is_ignored=False):
        self.name = name
        self.expr = expr
        self.is_ignored = is_ignored

    def _eval(self, env):
        return Rule(self.name, self.expr._eval(env), is_ignored=self.is_ignored)

    def _compile(self, out):
        return self.expr._compile(out)


class Seq:
    def __init__(self, *exprs, constructor=None):
        if isinstance(constructor, type):
            constructor = constructor.__name__
        self.exprs = exprs
        self.constructor = constructor

    def _eval(self, env):
        return Seq(*[x._eval(env) for x in self.exprs], constructor=self.constructor,)

    def _compile(self, out):
        end = out.reserve('end_sequence')
        items = []
        for expr in self.exprs:
            out.compile(expr)
            with out.IF_NOT('_mode'):
                out.goto(end)
            item = out.define('item', '_result')
            items.append(item)

        values = ', '.join(items)
        if self.constructor is None:
            value = f'[{values}]'
        else:
            value = f'{self.constructor}({values})'
        out.set('_result', value)
        out.label(end)


class Skip:
    def __init__(self, *exprs):
        self.exprs = exprs

    def _eval(self, env):
        return Skip(*[x._eval(env) for x in self.exprs])

    def _compile(self, out):
        checkpoint = out.define('checkpoint', '_pos')
        loop = out.reserve('loop_skip')

        out.label(loop)
        for expr in self.exprs:
            out.compile(expr)
            with out.IF('_mode'):
                out.set(checkpoint, '_pos')
                out.goto(loop)

        out.set('_mode', True)
        out.set('_result', None)
        out.set('_pos', checkpoint)


def Some(expr):
    return List(expr, allow_empty=False)


class StringLiteral:
    def __init__(self, value):
        if not isinstance(value, str):
            raise TypeError(f'Expected str. Received: {type(value)}.')
        self.value = value

    def _eval(self, env):
        return self

    def _compile(self, out):
        if self.value == '':
            out.set('_mode', True)
            out.set('_result', "''")
            return

        value = out.define('value', repr(self.value))
        end = out.define('end', f'_pos + {len(self.value)}')
        with out.IF(f'_text[_pos:{end}] == {value}'):
            out.set('_pos', end)
            out.skip_ignored()
            out.set('_mode', True)
            out.set('_result', value)
        with out.ELSE():
            out.set('_mode', False)
            out.set('_result', id(self))


class Template:
    def __init__(self, name, params, expr):
        self.name = name
        self.params = params
        self.expr = expr

    def __call__(self, *args, **kwargs):
        sub = {}
        for param, arg in zip(self.params, args):
            sub[param] = arg
        # TODO: Raise an exception if any kwargs aren't actual parameters.
        sub.update(kwargs)
        return self.expr._eval(sub)

    def _eval(self, env):
        return Template(self.name, self.params, self.expr._eval(env))


class OperatorPrecedence:
    def __init__(self, atom, *rules):
        self.atom = atom
        self.rules = rules

    def _eval(self, env):
        return OperatorPrecedence(
            self.atom._eval(env), *[x._eval(env) for x in self.rules],
        )

    def _compile(self, out):
        prev = self.atom
        for rule in self.rules:
            rule.operand = prev
            prev = rule
        prev._compile(out)


class OperatorPrecedenceRule:
    def __init__(self, *operators):
        self.operators = operators[0] if len(operators) == 1 else Choice(*operators)
        self.operand = None

    def _eval(self, env):
        result = self.__class__(self.operators._eval(env))
        if self.operand is not None:
            result.operand = self.operand._eval(env)
        return result


class LeftAssoc(OperatorPrecedenceRule):
    def _compile(self, out):
        operand_part = out.reserve('left_assoc_operand')
        loop = out.reserve('loop_left_assoc')
        succeed = out.reserve('suceed_left_assoc')
        end = out.reserve('end_left_assoc')

        staging = out.define('staging', None)
        checkpoint = out.define('checkpoint', '_pos')
        is_first = out.define('is_first', True)

        out.goto(operand_part)

        out.label(loop)
        out.compile(self.operators)

        with out.IF_NOT('_mode'):
            out.goto(succeed)

        operator = out.define('operator', '_result')

        out.label(operand_part)
        out.compile(self.operand)

        with out.IF_NOT('_mode'):
            with out.IF(is_first):
                out.goto(end)
            with out.ELSE():
                out.goto(succeed)

        out.set(checkpoint, '_pos')

        with out.IF(is_first):
            out.set(is_first, False)
            out.set(staging, '_result')

        with out.ELSE():
            out.set(staging, f'Infix({staging}, {operator}, _result)')

            if isinstance(self, NonAssoc):
                out.goto(succeed)

        out.goto(loop)

        out.label(succeed)
        out.set('_mode', True)
        out.set('_result', staging)
        out.set('_pos', checkpoint)

        out.label(end)


class NonAssoc(LeftAssoc):
    pass


class RightAssoc(OperatorPrecedenceRule):
    def _compile(self, out):
        backup = out.define('backup', None)
        prev = out.define('prev', None)

        staging = out.reserve('staging')
        checkpoint = out.define('checkpoint', '_pos')

        loop = out.reserve('loop_right_assoc')
        end = out.reserve('end_right_assoc')

        out.label(loop)
        out.compile(self.operand)

        with out.IF_NOT('_mode'):
            with out.IF(prev):
                with out.IF(backup):
                    out.set(f'{backup}.right', f'{prev}.left')
                    out.set('_result', staging)
                with out.ELSE():
                    out.set('_result', f'{prev}.left')
                out.set('_mode', True)
                out.set('_pos', checkpoint)
            out.goto(end)

        operand = out.define('operand', '_result')
        out.set(checkpoint, '_pos')
        out.compile(self.operators)

        with out.IF('_mode'):
            step = f'Infix({operand}, _result, None)'

            with out.IF(prev):
                out.set(backup, prev)
                out(f'{backup}.right = {prev} = {step}')

            with out.ELSE():
                out(f'{staging} = {prev} = {step}')

            out.goto(loop)

        out.set('_mode', True)
        out.set('_pos', checkpoint)

        with out.IF(prev):
            out.set(f'{prev}.right', operand)
            out.set('_result', staging)

        with out.ELSE():
            out.set('_result', operand)

        out.label(end)


class Postfix(OperatorPrecedenceRule):
    def _compile(self, out):
        out.compile(self.operand)

        loop = out.reserve('loop_postfix')
        end = out.reserve('end_postfix')

        with out.IF_NOT('_mode'):
            out.goto(end)

        staging = out.define('staging', '_result')
        checkpoint = out.define('checkpoint', '_pos')

        out.label(loop)
        out.compile(self.operators)

        with out.IF('_mode'):
            out.set(staging, f'Postfix({staging}, _result)')
            out.set(checkpoint, '_pos')
            out.goto(loop)

        with out.ELSE():
            out.set('_mode', True)
            out.set('_result', staging)
            out.set('_pos', checkpoint)

        out.label(end)


class Prefix(OperatorPrecedenceRule):
    def _compile(self, out):
        loop = out.reserve('loop_prefix')
        end = out.reserve('end_prefix')

        checkpoint = out.define('checkpoint', '_pos')
        staging = out.define('staging', None)
        prev = out.define('prev', None)

        out.label(loop)
        out.compile(self.operators)

        with out.IF('_mode'):
            out.set(checkpoint, '_pos')
            step = out.define('step', 'Prefix(_result, None)')
            with out.IF(f'{prev} is None'):
                out(f'{prev} = {staging} = {step}')

            with out.ELSE():
                out.set(f'{prev}.right', step)
                out.set(prev, step)

            out.goto(loop)

        out.set('_pos', checkpoint)
        out.compile(self.operand)

        with out.IF(f'{prev} and _mode'):
            out.set(f'{prev}.right', '_result')
            out.set('_result', staging)

        out.label(end)


class PythonExpression:
    def __init__(self, source_code):
        self.source_code = source_code

    def _eval(self, env):
        return self

    def _compile(self, out):
        out.set('_mode', True)
        out.set('_result', self.source_code)


class PythonSection:
    def __init__(self, source_code):
        self.source_code = source_code

    def _eval(self, env):
        return self


class Where:
    def __init__(self, expr, predicate):
        self.expr = expr
        self.predicate = predicate

    def _eval(self, env):
        return Where(
            expr=self.expr._eval(env),
            predicate=self.predicate._eval(env),
        )

    def _compile(self, out):
        out.compile(self.expr)
        end = out.reserve('end_where')

        with out.IF('_mode'):
            arg = out.define('arg', '_result')

        with out.ELSE():
            out.goto(end)

        out.compile(self.predicate)

        with out.IF('_mode'):
            with out.IF(f'_result({arg})'):
                out.set('_mode', True)
                out.set('_result', arg)

            with out.ELSE():
                out.set('_mode', False)
                out.set('_result', id(self))

        out.label(end)
