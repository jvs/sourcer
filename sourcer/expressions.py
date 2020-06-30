import typing


class Alt:
    def __init__(self, expr, separator, allow_trailer=False, allow_empty=True):
        self.expr = expr
        self.separator = separator
        self.allow_trailer = allow_trailer
        self.allow_empty = allow_empty

    def __repr__(self):
        result = f'Alt({self.expr!r}, {self.separator!r}'
        if self.allow_trailer:
            result += ', allow_trailer=True'
        if not self.allow_empty:
            result += ', allow_empty=False'
        return result + ')'

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

        out('while True:')
        with out.indented():
            item = out.compile(self.expr)

            with out.IF_NOT(out.is_success(item)):
                with out.IF(out.is_error(item)):
                    out.copy_result(target, item)
                out('break')

            out(f'{buf}.append({item.value})')
            if self.allow_trailer:
                out.set('pos', item.pos)
            else:
                out(f'pos = {target.pos} = {item.pos}')

            sep = out.compile(self.separator)

            with out.IF_NOT(out.is_success(sep)):
                with out.IF(out.is_error(sep)):
                    out.copy_result(target, sep)
                out('break')

            out.set('pos', sep.pos)

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

    def __repr__(self):
        return f'Apply({self.expr1!r}, {self.expr2!r}, apply_left={self.apply_left!r})'

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

    def __repr__(self):
        return f'Call({self.func!r}, {self.args!r})'

    def _eval(self, env):
        func = self.func._eval(env)
        if callable(func):
            return func(
                *[x._eval(env) for x in self.args if not isinstance(x, KeywordArg)],
                **{
                    x.name: x._eval(env) for x in self.args if isinstance(x, KeywordArg)
                },
            )
        else:
            raise Exception(f'Not callable: {func!r}')


class Choice:
    def __init__(self, *exprs):
        self.exprs = exprs

    def __repr__(self):
        values = ', '.join(repr(x) for x in self.exprs)
        return f'Choice({values})'

    def _eval(self, env):
        return Choice(*[x._eval(env) for x in self.exprs])

    def _compile(self, out, target):
        backtrack = out.define('backtrack', 'pos')
        end = out.reserve('end_choice')
        items = []
        for expr in self.exprs:
            item = out.compile(expr)
            items.append(item)
            with out.IF(f'{out.is_success(item)} or {out.is_error(item)}'):
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

    def __repr__(self):
        args = [repr(self.name), repr(self.fields)]
        if self.is_ignored:
            args.append('is_ignored=True')
        return f'Class({", ".join(args)})'

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


class Drop:
    def __init__(self, expr1, expr2, drop_left=True):
        self.expr1 = expr1
        self.expr2 = expr2
        self.drop_left = drop_left

    def __repr__(self):
        func = 'Right' if self.drop_left else 'Left'
        return f'{func}({self.expr1!r}, {self.expr2!r})'

    def _eval(self, env):
        return Drop(
            expr1=self.expr1._eval(env),
            expr2=self.expr2._eval(env),
            drop_left=self.drop_left,
        )

    def _compile(self, out, target):
        item1 = out.compile(self.expr1)

        with out.IF_NOT(out.is_success(item1)):
            out.copy_result(target, item1)

        with out.ELSE():
            out.set('pos', item1.pos)

            if self.drop_left:
                out.compile(self.expr2, target)
            else:
                item2 = out.compile(self.expr2)
                with out.IF(out.is_success(item2)):
                    out.succeed(target, item1.value, item2.pos)
                with out.ELSE():
                    out.copy_result(target, item2)


class Fail:
    def __init__(self, message):
        self.message = None

    def __repr__(self):
        return f'Fail({self.message!r})'

    def _eval(self, env):
        return self

    def _compile(self, out, target):
        out.fail(target, self, 'pos')


class KeywordArg:
    def __init__(self, name, expr):
        self.name = name
        self.expr = expr

    def __repr__(self):
        return f'KeywordArg({self.name!r}, {self.expr!r})'

    def _eval(self, env):
        return KeywordArg(self.name, self.expr._eval(env))


def Left(expr1, expr2):
    return Drop(expr1, expr2, drop_left=False)


class List:
    def __init__(self, expr, allow_empty=True):
        self.expr = expr
        self.allow_empty = allow_empty

    def __repr__(self):
        cls = 'List' if self.allow_empty else 'Some'
        return f'{cls}({self.expr!r})'

    def _eval(self, env):
        return List(expr=self.expr._eval(env), allow_empty=self.allow_empty)

    def _compile(self, out, target):
        buf = out.define('buf', '[]')
        out('while True:')
        with out.indented():
            item = out.compile(self.expr)

            with out.IF_NOT(out.is_success(item)):
                with out.IF(out.is_error(item)):
                    out.copy_result(target, item)
                out('break')

            with out.IF(f'{item.mode} != {out.IGNORE}'):
                out(f'{buf}.append({item.value})')

            out(f'pos = {item.pos}')

        if not self.allow_empty:
            with out.IF(f'not {buf}'):
                out.fail(target, self, 'pos')
            out('else:')
            out.indent += 1

        out.succeed(target, buf, 'pos')


class Opt:
    def __init__(self, expr):
        self.expr = expr

    def __repr__(self):
        return f'Opt({self.expr!r})'

    def _eval(self, env):
        return Opt(self.expr._eval(env))

    def _compile(self, out, target):
        backtrack = out.define('backtrack', 'pos')
        item = out.compile(self.expr)
        with out.IF(f'{out.is_success(item)} or {out.is_error(item)}'):
            out.copy_result(target, item)
        with out.ELSE():
            out.succeed(target, 'None', backtrack)


class Pass:
    def __init__(self, value):
        self.value = value

    def __repr__(self):
        return f'Pass({self.value!r})'

    def _eval(self, env):
        return self

    def _compile(self, out, target):
        out.succeed(target, repr(self.value), 'pos')


class Ref:
    def __init__(self, name):
        self.name = name

    def __repr__(self):
        return f'Ref({self.name!r})'

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

    def __repr__(self):
        return f'RegexLiteral({self.pattern!r})'

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
    return Drop(expr1, expr2, drop_left=True)


class Rule:
    def __init__(self, name, expr, is_ignored=False):
        self.name = name
        self.expr = expr
        self.is_ignored = is_ignored

    def __repr__(self):
        extra = ', is_ignored=True' if self.is_ignored else ''
        return f'Rule({self.name!r}, {self.expr!r}{extra})'

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

    def __repr__(self):
        values = ', '.join(repr(x) for x in self.exprs)
        if self.constructor is None:
            return f'Seq({values})'
        else:
            return f'Seq({values}, constructor={self.constructor!r})'

    def _eval(self, env):
        return Seq(*[x._eval(env) for x in self.exprs], constructor=self.constructor,)

    def _compile(self, out, target):
        items = []
        for expr in self.exprs:
            item = out.compile(expr)
            items.append(item)
            with out.IF_NOT(out.is_success(item)):
                out.copy_result(target, item)
            out('else:')
            out.indent += 1
            out(f'pos = {item.pos}')

        values = ', '.join(x.value for x in items)
        if self.constructor is None:
            value = f'[{values}]'
        else:
            value = f'{self.constructor}({values})'
        out.succeed(target, value, 'pos')


class Skip:
    def __init__(self, expr):
        self.expr = expr

    def __repr__(self):
        return f'Skip({self.expr!r})'

    def _eval(self, env):
        return Skip(self.expr._eval(env))

    def _compile(self, out, target):
        out('while True:')
        with out.indented():
            item = out.compile(self.expr)

            with out.IF(out.is_success(item)):
                out.set('pos', item.pos)

            with out.ELSE():
                with out.IF(out.is_error(item)):
                    out.copy_result(target, item)
                out('break')

        out.succeed(target, None, 'pos')


def Some(expr):
    return List(expr, allow_empty=False)


class StringLiteral:
    def __init__(self, value):
        if not isinstance(value, str):
            raise TypeError(f'Expected str. Received: {type(value)}.')
        self.value = value

    def __repr__(self):
        return f'Literal({self.value!r})'

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

    def __repr__(self):
        return f'Template({self.name!r}, {self.params!r}, {self.expr!r})'

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

    def __repr__(self):
        rules = ', '.join(repr(x) for x in self.rules)
        return f'OperatorPrecedence({self.atom!r}, {rules})'

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

    def __repr__(self):
        return f'{self.__class__.__name__}({self.operators!r})'

    def _eval(self, env):
        result = self.__class__(self.operators._eval(env))
        if self.operand is not None:
            result.operand = self.operand._eval(env)
        return result


class LeftAssoc(OperatorPrecedenceRule):
    def _compile(self, out, target):
        is_first = out.define('is_first', True)
        out('while True:')
        with out.indented():
            with out.IF(f'not {is_first}'):
                operator = out.compile(self.operators)

                with out.IF_NOT(out.is_success(operator)):
                    with out.IF(out.is_error(operator)):
                        out.copy_result(target, operator)
                    out('break')

                out.set('pos', operator.pos)

            item = out.compile(self.operand)

            with out.IF_NOT(out.is_success(item)):
                with out.IF(f'{is_first} or {out.is_error(item)}'):
                    out.copy_result(target, item)
                out('break')

            out(f'pos = {target.pos} = {item.pos}')

            with out.IF(is_first):
                out.set(is_first, False)
                out.set(target.value, item.value)
                out.set(target.mode, out.SUCCESS)

            with out.ELSE():
                value = f'Infix({target.value}, {operator.value}, {item.value})'
                out.set(target.value, value)

                if isinstance(self, NonAssoc):
                    out('break')


class NonAssoc(LeftAssoc):
    pass


class RightAssoc(OperatorPrecedenceRule):
    def _compile(self, out, target):
        backup = out.define('backup', None)
        prev = out.define('prev', None)
        out('while True:')
        with out.indented():
            item = out.compile(self.operand)

            with out.IF_NOT(out.is_success(item)):
                with out.IF(f'{out.is_error(item)} or {prev} is None'):
                    out.copy_result(target, item)

                with out.ELIF(f'{backup} is None'):
                    out.set(target.value, f'{prev}.left')
                    out.set(target.mode, out.SUCCESS)

                with out.ELSE():
                    out.set(f'{backup}.right', f'{prev}.left')

                out('break')

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

            with out.ELSE():
                with out.IF(out.is_error(operator)):
                    out.copy_result(target, operator)

                with out.ELIF(f'{prev} is None'):
                    out.set(target.mode, out.SUCCESS)
                    out.set(target.value, item.value)

                with out.ELSE():
                    out.set(target.mode, out.SUCCESS)
                    out.set(f'{prev}.right', item.value)

                out('break')


class Postfix(OperatorPrecedenceRule):
    def _compile(self, out, target):
        item = out.compile(self.operand)
        out.copy_result(target, item)

        with out.IF(out.is_success(item)):
            out.set('pos', item.pos)
            out('while True:')
            with out.indented():
                op = out.compile(self.operators)

                with out.IF_NOT(out.is_success(op)):
                    with out.IF(out.is_error(op)):
                        out.copy_result(target, op)
                    with out.ELSE():
                        out.set(target.pos, 'pos')
                    out('break')

                out.set('pos', op.pos)
                out.set(target.value, f'Postfix({target.value}, {op.value})')


class Prefix(OperatorPrecedenceRule):
    def _compile(self, out, target):
        prev = out.define('prev', None)
        out('while True:')
        with out.indented():
            op = out.compile(self.operators)

            with out.IF(out.is_success(op)):
                out.set('pos', op.pos)

                with out.IF(f'{prev} is None'):
                    out(f'{target.value} = {prev} = Prefix({op.value}, None)')

                with out.ELSE():
                    value = out.define('value', f'Prefix({op.value}, None)')
                    out.set(f'{prev}.right', value)
                    out.set(prev, value)

            with out.ELSE():
                with out.IF(out.is_error(op)):
                    out.copy_result(target, op)
                    out('break')

                item = out.compile(self.operand)
                with out.IF(f'{prev} is None or not {out.is_success(item)}'):
                    out.copy_result(target, item)

                with out.ELSE():
                    out.set(f'{prev}.right', item.value)
                    out.set(target.pos, item.pos)
                    out.set(target.mode, out.SUCCESS)

                out('break')


class PythonExpression:
    def __init__(self, source_code):
        self.source_code = source_code

    def __repr__(self):
        return f'PythonExpression({self.source_code!r})'

    def _eval(self, env):
        return self

    def _compile(self, out, target):
        out.succeed(target, self.source_code, 'pos')


class PythonSection:
    def __init__(self, source_code):
        self.source_code = source_code

    def __repr__(self):
        return f'PythonSection({self.source_code!r})'

    def _eval(self, env):
        return self
