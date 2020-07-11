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

    def _compile(self, out, target):
        buf = out.define('buf', '[]')
        out(f'{target.pos} = pos')

        loop = out.reserve('loop_alt')
        end = out.reserve('end_alt')

        out.label(loop)
        item = out.compile(self.expr)

        with out.IF_NOT(out.is_success(item)):
            out.goto(end)

        out(f'{buf}.append({item.value})')
        if self.allow_trailer:
            out.set('pos', item.pos)
        else:
            out(f'pos = {target.pos} = {item.pos}')

        sep = out.compile(self.separator)

        with out.IF_NOT(out.is_success(sep)):
            out.goto(end)

        out.set('pos', sep.pos)
        out.goto(loop)

        out.label(end)

        if not self.allow_empty:
            with out.IF(f'not {buf}'):
                out.fail(target, self, 'pos')
            out('else:')
            out.indent += 1

        # out.succeed:
        out.set(target.mode, out.SUCCESS)
        out.set(target.value, buf)
        if self.allow_trailer:
            out.set(target.pos, 'pos')


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

    def _compile(self, out, target):
        item1 = out.compile(self.expr1)
        end = out.reserve('end_apply')

        with out.IF_NOT(out.is_success(item1)):
            out.copy_result(target, item1)
            out.goto(end)

        out.set('pos', item1.pos)
        item2 = out.compile(self.expr2)
        func, arg = (item1, item2) if self.apply_left else (item2, item1)

        with out.IF(out.is_success(func)):
            out.succeed(target, f'{func.value}({arg.value})', item2.pos)

        with out.ELSE():
            out.copy_result(target, item2)

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

    def _compile(self, out, target):
        backtrack = out.define('backtrack', 'pos')
        end = out.reserve('end_choice')
        items = []
        for expr in self.exprs:
            item = out.compile(expr)
            items.append(item)
            with out.IF(out.is_success(item)):
                out.copy_result(target, item)
                out.goto(end)
            out.set('pos', backtrack)

        out.fail(target, self, 'pos')
        for item in items:
            with out.IF(f'{target.pos} < {item.pos}'):
                out.copy_result(target, item)

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

    def _compile(self, out, target):
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
        delegate = Seq(*exprs, constructor=self.name)
        return out.compile(delegate, target=target)


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

    def _compile(self, out, target):
        item1 = out.compile(self.expr1)
        end = out.reserve('end_discard')

        with out.IF_NOT(out.is_success(item1)):
            out.copy_result(target, item1)
            out.goto(end)

        out.set('pos', item1.pos)

        if self.discard_left:
            out.compile(self.expr2, target)
        else:
            item2 = out.compile(self.expr2)
            with out.IF(out.is_success(item2)):
                out.succeed(target, item1.value, item2.pos)
            with out.ELSE():
                out.copy_result(target, item2)

        out.label(end)


class Expect:
    def __init__(self, expr):
        self.expr = expr

    def _eval(self, env):
        return Expect(self.expr._eval(env))

    def _compile(self, out, target):
        backtrack = out.define('backtrack', 'pos')
        item = out.compile(self.expr)
        out.set(target.mode, item.mode)
        out.set(target.value, None)
        out.set(target.pos, backtrack)


class ExpectNot:
    def __init__(self, expr):
        self.expr = expr

    def _eval(self):
        return ExpectNot(self.expr._eval(env))

    def _compile(self, out, target):
        backtrack = out.define('backtrack', 'pos')
        item = out.compile(self.expr)
        with out.IF(out.is_success(item)):
            out.fail(target, self, backtrack)
        with out.ELSE():
            out.succeed(target, None, backtrack)


class Fail:
    def __init__(self, message):
        self.message = None

    def _eval(self, env):
        return self

    def _compile(self, out, target):
        out.fail(target, self, 'pos')


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

    def _compile(self, out, target):
        buf = out.define('buf', '[]')
        loop = out.reserve('loop_list')
        end = out.reserve('end_list')

        out.label(loop)
        item = out.compile(self.expr)

        with out.IF_NOT(out.is_success(item)):
            out.goto(end)

        out(f'{buf}.append({item.value})')
        out.set('pos', item.pos)
        out.goto(loop)
        out.label(end)

        if self.allow_empty:
            out.succeed(target, buf, 'pos')
        else:
            with out.IF(f'not {buf}'):
                out.fail(target, self, 'pos')

            with out.ELSE():
                out.succeed(target, buf, 'pos')


class Opt:
    def __init__(self, expr):
        self.expr = expr

    def _eval(self, env):
        return Opt(self.expr._eval(env))

    def _compile(self, out, target):
        backtrack = out.define('backtrack', 'pos')
        item = out.compile(self.expr)
        with out.IF(out.is_success(item)):
            out.copy_result(target, item)
        with out.ELSE():
            out.succeed(target, 'None', backtrack)


class Pass:
    def __init__(self, value):
        self.value = value

    def _eval(self, env):
        return self

    def _compile(self, out, target):
        out.succeed(target, repr(self.value), 'pos')


class Ref:
    def __init__(self, name):
        self.name = name

    def _eval(self, env):
        return env.get(self.name, self)

    def _compile(self, out, target):
        rule = out.rule_map[self.name]
        out(
            f'{target.mode}, {target.value}, {target.pos}'
            f' = yield ({out.CONTINUE}, {rule}, pos)'
        )


class RegexLiteral:
    def __init__(self, pattern):
        if isinstance(pattern, typing.Pattern):
            pattern = pattern.pattern
        if not isinstance(pattern, str):
            raise TypeError('Expected str')
        self.pattern = pattern

    def _eval(self, env):
        return self

    def _compile(self, out, target):
        out.add_import('re')
        pattern = out.define_constant('pattern', f're.compile({self.pattern!r})')
        match = out.define('match', f'{pattern}.match(text, pos)')

        with out.IF(match):
            out.succeed(target, f'{match}.group(0)', f'{match}.end()', skip_ignored=True)

        with out.ELSE():
            out.fail(target, self, 'pos')


def Right(expr1, expr2):
    return Discard(expr1, expr2, discard_left=True)


class Rule:
    def __init__(self, name, expr, is_ignored=False):
        self.name = name
        self.expr = expr
        self.is_ignored = is_ignored

    def _eval(self, env):
        return Rule(self.name, self.expr._eval(env), is_ignored=self.is_ignored)

    def _compile(self, out, target):
        return self.expr._compile(out, target)


class Seq:
    def __init__(self, *exprs, constructor=None):
        if isinstance(constructor, type):
            constructor = constructor.__name__
        self.exprs = exprs
        self.constructor = constructor

    def _eval(self, env):
        return Seq(*[x._eval(env) for x in self.exprs], constructor=self.constructor,)

    def _compile(self, out, target):
        end = out.reserve('end_sequence')
        items = []
        for expr in self.exprs:
            item = out.compile(expr)
            items.append(item)
            with out.IF_NOT(out.is_success(item)):
                out.copy_result(target, item)
                out.goto(end)
            out(f'pos = {item.pos}')

        values = ', '.join(x.value for x in items)
        if self.constructor is None:
            value = f'[{values}]'
        else:
            value = f'{self.constructor}({values})'
        out.succeed(target, value, 'pos')
        out.label(end)


class Skip:
    def __init__(self, expr):
        self.expr = expr

    def _eval(self, env):
        return Skip(self.expr._eval(env))

    def _compile(self, out, target):
        loop = out.reserve('loop_skip')
        end = out.reserve('end_skip')

        out.label(loop)
        item = out.compile(self.expr)

        with out.IF(out.is_success(item)):
            out.set('pos', item.pos)
            out.goto(loop)

        with out.ELSE():
            out.succeed(target, None, 'pos')


def Some(expr):
    return List(expr, allow_empty=False)


class StringLiteral:
    def __init__(self, value):
        if not isinstance(value, str):
            raise TypeError(f'Expected str. Received: {type(value)}.')
        self.value = value

    def _eval(self, env):
        return self

    def _compile(self, out, target):
        if self.value == '':
            out.succeed(target, "''", 'pos')
            return

        value = out.define('value', repr(self.value))
        end = out.define('end', f'pos + {len(self.value)}')
        with out.IF(f'text[pos:{end}] == {value}'):
            out.succeed(target, value, end, skip_ignored=True)
        with out.ELSE():
            out.fail(target, self, 'pos')


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

    def _compile(self, out, target):
        prev = self.atom
        for rule in self.rules:
            rule.operand = prev
            prev = rule
        return prev._compile(out, target)


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
    def _compile(self, out, target):
        operand_part = out.reserve('left_assoc_operand')
        loop = out.reserve('loop_left_assoc')
        end = out.reserve('end_left_assoc')

        is_first = out.define('is_first', True)
        out.goto(operand_part)
        out.label(loop)
        operator = out.compile(self.operators)

        with out.IF_NOT(out.is_success(operator)):
            out.goto(end)

        out.set('pos', operator.pos)

        out.label(operand_part)
        item = out.compile(self.operand)

        with out.IF_NOT(out.is_success(item)):
            with out.IF(is_first):
                out.copy_result(target, item)
            out.goto(end)

        out(f'pos = {target.pos} = {item.pos}')

        with out.IF(is_first):
            out.set(is_first, False)
            out.set(target.value, item.value)
            out.set(target.mode, out.SUCCESS)

        with out.ELSE():
            value = f'Infix({target.value}, {operator.value}, {item.value})'
            out.set(target.value, value)

            if isinstance(self, NonAssoc):
                out.goto(end)

        out.goto(loop)
        out.label(end)


class NonAssoc(LeftAssoc):
    pass


class RightAssoc(OperatorPrecedenceRule):
    def _compile(self, out, target):
        backup = out.define('backup', None)
        prev = out.define('prev', None)

        loop = out.reserve('loop_right_assoc')
        end = out.reserve('end_right_assoc')

        out.label(loop)
        item = out.compile(self.operand)

        with out.IF_NOT(out.is_success(item)):
            with out.IF(f'{prev} is None'):
                out.copy_result(target, item)

            with out.ELIF(f'{backup} is None'):
                out.set(target.value, f'{prev}.left')
                out.set(target.mode, out.SUCCESS)

            with out.ELSE():
                out.set(f'{backup}.right', f'{prev}.left')

            out.goto(end)

        out(f'pos = {target.pos} = {item.pos}')
        operator = out.compile(self.operators)

        with out.IF(out.is_success(operator)):
            value = f'Infix({item.value}, {operator.value}, None)'

            with out.IF(f'{prev} is None'):
                out.set(prev, value)
                out.set(target.value, prev)

            with out.ELSE():
                out.set(backup, prev)
                out(f'{backup}.right = {prev} = {value}')

            out.goto(loop)

        with out.IF(f'{prev} is None'):
            out.set(target.mode, out.SUCCESS)
            out.set(target.value, item.value)

        with out.ELSE():
            out.set(target.mode, out.SUCCESS)
            out.set(f'{prev}.right', item.value)

        out.label(end)


class Postfix(OperatorPrecedenceRule):
    def _compile(self, out, target):
        item = out.compile(self.operand)
        out.copy_result(target, item)

        loop = out.reserve('loop_postfix')
        end = out.reserve('end_postfix')

        with out.IF_NOT(out.is_success(item)):
            out.goto(end)

        out.set('pos', item.pos)
        out.label(loop)
        op = out.compile(self.operators)

        with out.IF(out.is_success(op)):
            out.set('pos', op.pos)
            out.set(target.value, f'Postfix({target.value}, {op.value})')
            out.goto(loop)

        with out.ELSE():
            out.set(target.pos, 'pos')

        out.label(end)


class Prefix(OperatorPrecedenceRule):
    def _compile(self, out, target):
        loop = out.reserve('loop_prefix')
        end = out.reserve('end_prefix')
        prev = out.define('prev', None)

        out.label(loop)
        op = out.compile(self.operators)

        with out.IF(out.is_success(op)):
            out.set('pos', op.pos)

            with out.IF(f'{prev} is None'):
                out(f'{target.value} = {prev} = Prefix({op.value}, None)')

            with out.ELSE():
                value = out.define('value', f'Prefix({op.value}, None)')
                out.set(f'{prev}.right', value)
                out.set(prev, value)

            out.goto(loop)

        item = out.compile(self.operand)
        with out.IF(f'{prev} is None or not {out.is_success(item)}'):
            out.copy_result(target, item)

        with out.ELSE():
            out.set(f'{prev}.right', item.value)
            out.set(target.pos, item.pos)
            out.set(target.mode, out.SUCCESS)

        out.label(end)


class PythonExpression:
    def __init__(self, source_code):
        self.source_code = source_code

    def _eval(self, env):
        return self

    def _compile(self, out, target):
        out.succeed(target, self.source_code, 'pos')


class PythonSection:
    def __init__(self, source_code):
        self.source_code = source_code

    def _eval(self, env):
        return self
