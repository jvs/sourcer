import typing


class Alt:
    def __init__(self, expr, separator, allow_trailer=False, allow_empty=True):
        self.expr = conv(expr)
        self.separator = conv(separator)
        self.allow_trailer = allow_trailer
        self.allow_empty = allow_empty

    def __repr__(self):
        result = f'Alt({self.expr!r}, {self.separator!r}'
        if self.allow_trailer:
            result += ', allow_trailer=True'
        if not self.allow_empty:
            result += ', allow_empty=False'
        return result + ')'

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
        out.set(target.mode, True)
        out.set(target.value, buf)
        if self.allow_trailer:
            out.set(target.pos, 'pos')


class Choice:
    def __init__(self, *exprs):
        self.exprs = [conv(x) for x in exprs]

    def __repr__(self):
        values = ', '.join(repr(x) for x in self.exprs)
        return f'Choice({values})'

    def _compile(self, out, target):
        items = []
        for expr in self.exprs:
            item = out.compile(expr)
            items.append(item)
            with out.IF(f'{out.is_success(item)} or {out.is_error(item)}'):
                out.copy_result(target, item)
            out('else:')
            out.indent += 1

        out.fail(target, self, 'pos')
        for item in items:
            with out.IF(f'{target.pos} < {item.pos}'):
                out.copy_result(target, item)


class Drop:
    def __init__(self, expr1, expr2, drop_left=True):
        self.expr1 = conv(expr1)
        self.expr2 = conv(expr2)
        self.drop_left = drop_left

    def __repr__(self):
        return f'Drop({self.expr1!r}, {self.expr2!r}, drop_left={self.drop_left})'

    def _compile(self, out, target):
        item1 = out.compile(self.expr1)

        with out.IF_NOT(out.is_success(item1)):
            out.copy_result(target, item1)

        with out.ELSE():
            out.set('pos', item1.pos)
            item2 = out.compile(self.expr2)

            if self.drop_left:
                out.copy_result(target, item2)
            else:
                with out.IF(out.is_success(item2)):
                    out.succeed(target, item1.value, item2.pos)
                with out.ELSE():
                    out.copy_result(target, item2)


def Left(expr1, expr2):
    return Drop(expr1, expr2, drop_left=False)


class List:
    def __init__(self, expr, allow_empty=True):
        self.expr = conv(expr)
        self.allow_empty = allow_empty

    def __repr__(self):
        cls = 'List' if self.allow_empty else 'Some'
        return f'{cls}({self.expr!r})'

    def _compile(self, out, target):
        buf = out.define('buf', '[]')
        out('while True:')
        with out.indented():
            item = out.compile(self.expr)

            with out.IF_NOT(out.is_success(item)):
                with out.IF(out.is_error(item)):
                    out.copy_result(target, item)
                out('break')

            condition = (
                f'not isinstance({item.value}, Token) or '
                f'not {item.value}._is_ignored'
            )
            with out.IF(condition):
                out(f'{buf}.append({item.value})')

            out(f'pos = {item.pos}')

        if not self.allow_empty:
            with out.IF(f'not {buf}'):
                out.fail(target, self, 'pos')
            out('else:')
            out.indent += 1

        out.succeed(target, buf, 'pos')


class Literal:
    def __init__(self, value):
        self.value = value

    def __repr__(self):
        return f'Literal({self.value!r})'

    def _compile(self, out, target):
        value = out.define('value', repr(self.value))
        with out.IF('isinstance(text, str)'):
            self._compile_for_text(out, target, value)
        with out.ELSE():
            self._compile_for_items(out, target, value)

    def _compile_for_text(self, out, target, value):
        if not isinstance(self.value, str):
            out.fail(target, self, 'pos')
            return
        end = out.define('end', f'pos + {len(self.value)}')
        with out.IF(f'text[pos:{end}] == {value}'):
            out.succeed(target, value, end)
        with out.ELSE():
            out.fail(target, self, 'pos')

    def _compile_for_items(self, out, target, value):
        with out.IF(f'pos < len(text) and text[pos] == {value}'):
            out.succeed(target, value, 'pos + 1')
        with out.ELSE():
            out.fail(target, self, 'pos')


class Opt:
    def __init__(self, expr):
        self.expr = conv(expr)

    def __repr__(self):
        return f'Opt({self.expr!r})'

    def _compile(self, out, target):
        item = out.compile(self.expr)
        with out.IF(f'{out.is_success(item)} or {out.is_error(item)}'):
            out.copy_result(target, item)
        with out.ELSE():
            out.succeed(target, 'None', 'pos')


class Ref:
    def __init__(self, name):
        self.name = name

    def __repr__(self):
        return f'Ref({self.name!r})'

    def _compile(self, out, target):
        rule = out.rule_map[self.name]
        out(f'{target.mode}, {target.value}, {target.pos} = yield (2, {rule}, pos)')


class Regex:
    def __init__(self, pattern):
        if isinstance(pattern, typing.Pattern):
            pattern = pattern.pattern
        if not isinstance(pattern, str):
            raise TypeError('Expected str')
        self.pattern = pattern

    def __repr__(self):
        return f'Regex({self.pattern!r})'

    def _compile(self, out, target):
        out.add_import('re')
        pattern = out.define_global('pattern', f're.compile({self.pattern!r})')

        with out.IF('isinstance(text, str)'):
            match = out.define('match', f'{pattern}.match(text, pos)')

            with out.IF(match):
                out.succeed(target, f'{match}.group(0)', f'{match}.end()')

            with out.ELSE():
                out.fail(target, self, 'pos')

        with out.ELIF('pos >= len(text)'):
            out.fail(target, self, 'pos')

        with out.ELSE():
            item = out.define('item', 'text[pos]')
            value = out.define('value',
                f'{item}.value if isinstance(item, Token) else item')
            match = out.define('match',
                f'{pattern}.fullmatch({value}) if isinstance({value}, str) else None')
            with out.IF(match):
                out.succeed(target, value, 'pos + 1')
            with out.ELSE():
                out.fail(target, self, 'pos')


def Right(expr1, expr2):
    return Drop(expr1, expr2, drop_left=True)


class Seq:
    def __init__(self, *exprs, constructor=None):
        self.exprs = [conv(x) for x in exprs]
        self.constructor = constructor

    def __repr__(self):
        values = ', '.join(repr(x) for x in self.exprs)
        if self.constructor is None:
            return f'Seq({values})'
        else:
            return f'Seq({values}, constructor={self.constructor!r})'

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
        self.expr = conv(expr)

    def __repr__(self):
        return f'Skip({self.expr!r})'

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


# Operator precedence parsing:

class OperatorPrecedence:
    def __init__(self, atom, *rules):
        self.atom = atom
        self.rules = rules

    def __repr__(self):
        rules = ', '.join(repr(x) for x in self.rules)
        return f'OperatorPrecedence({self.atom!r}, {rules})'

    def _compile(self, out, target):
        prev = self.atom
        for rule in self.rules:
            rule.operand = prev
            prev = rule
        return prev._compile(out, target)


class OperatorPrecedenceRule:
    def __init__(self, *operators):
        self.operators = conv(operators[0]) if len(operators) == 1 else Choice(*operators)
        self.operand = None

    def __repr__(self):
        return f'{self.__class__.__name__}({self.operators!r})'


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
                with out.IF(out.is_error(operator)):
                    out.copy_result(target, operator)
                out('break')

            out(f'pos = {target.pos} = {item.pos}')

            with out.IF(is_first):
                out.set(is_first, False)
                out.set(target.value, item.value)

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
                    out.set(target.mode, True)
                    out.set(target.value, f'{prev}.left')

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
                    out.set(target.mode, True)
                    out.set(target.value, item.value)

                with out.ELSE():
                    out.set(target.mode, True)
                    out.set(f'{prev}.right', item.value)

                out('break')


class Postfix(OperatorPrecedenceRule):
    def _compile(self, out, target):
        item = out.compile(self.operand)
        out.copy(target, item)

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
                    out.set(target.mode, True)

                out('break')


def conv(obj):
    """Converts a Python object to a parsing expression."""
    if hasattr(obj, '_compile'):
        return obj

    if isinstance(obj, (list, tuple)):
        return Seq(*obj)

    if isinstance(obj, typing.Pattern):
        return Regex(obj)
    else:
        return Literal(obj)
