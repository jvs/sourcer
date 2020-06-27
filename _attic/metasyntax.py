from ast import literal_eval
import types

from .builder import generate_source_code
from .expressions import *


meta = None


def _setup():
    global meta
    if meta:
        return
    meta = Grammar([
        Token('Space', Regex('[ \\t]+'), is_ignored=True),
        Token('Word', Regex('[_a-zA-Z][_a-zA-Z0-9]*')),
        Token('Symbol', Regex('<<\\!|\\!>>|<<|>>|=>|\\/\\/|[=;,:\\|\\/\\*\\+\\?\\!\\(\\)\\[\\]\\{\\}]')),
        Token('StringLiteral', Choice(Regex('("([^"\\\\]|\\\\.)*")'), Regex("('([^'\\\\]|\\\\.)*')"), Regex('("""([^\\\\]|\\\\.)*?""")'), Regex("('\\''([^\\\\]|\\\\.)*?'\\'')"))),
        Token('RegexLiteral', Regex('\\`([^\\`\\\\]|\\\\.)*\\`')),
        Token('Newline', Regex('[\\r\\n][\\s]*')),
        Token('Comment', Regex('#[^\\r\\n]*'), is_ignored=True),
        Rule('Sep', Some(Choice(Ref('Newline'), Literal(';')))),
        Rule('Name', Ref('Word')),
        Template('wrap', ['x'], Left(Right(Skip(Ref('Newline')), Ref('x')), Skip(Ref('Newline')))),
        Rule('Comma', Call(Ref('wrap'), [Literal(',')])),
        Class('RuleDef', [Rule('name', Left(Ref('Name'), Choice(Literal('='), Literal(':')))), Rule('expr', Ref('Expr'))]),
        Class('ClassDef', [Rule('name', Right(Literal('class'), Ref('Name'))), Rule('fields', Left(Right(Call(Ref('wrap'), [Literal('{')]), Alt(Ref('RuleDef'), Ref('Sep'), allow_trailer=True)), Literal('}')))]),
        Class('TokenDef', [Rule('is_ignored', Opt(Choice(Literal('ignore'), Literal('ignored')))), Rule('child', Right(Literal('token'), Choice(Ref('ClassDef'), Ref('RuleDef'))))]),
        Class('TemplateDef', [Rule('name', Right(Literal('template'), Ref('Name'))), Rule('params', Left(Right(Call(Ref('wrap'), [Literal('(')]), Alt(Call(Ref('wrap'), [Ref('Name')]), Ref('Comma'), allow_trailer=True)), Literal(')'))), Rule('expr', Right(Call(Ref('wrap'), [Choice(Literal('='), Literal(':'), Literal('=>'))]), Ref('Expr')))]),
        Rule('Def', Choice(Ref('TokenDef'), Ref('ClassDef'), Ref('TemplateDef'), Ref('RuleDef'))),
        Class('Ref', [Rule('name', Ref('Word'))]),
        Class('ListLiteral', [Rule('elements', Left(Right(Literal('['), Alt(Call(Ref('wrap'), [Ref('Expr')]), Ref('Comma'), allow_trailer=True)), Literal(']')))]),
        Rule('Atom', Choice(Left(Right(Literal('('), Call(Ref('wrap'), [Ref('Expr')])), Literal(')')), Ref('Ref'), Ref('StringLiteral'), Ref('RegexLiteral'), Ref('ListLiteral'))),
        Class('KeywordArg', [Rule('name', Left(Ref('Name'), Choice(Literal('='), Literal(':')))), Rule('expr', Ref('Expr'))]),
        Class('ArgList', [Rule('args', Left(Right(Literal('('), Alt(Call(Ref('wrap'), [Choice(Ref('KeywordArg'), Ref('Expr'))]), Ref('Comma'), allow_trailer=True)), Literal(')')))]),
        Rule('Expr', OperatorPrecedence(Ref('Atom'), Postfix(Ref('ArgList')), Postfix(Choice(Literal('?'), Literal('*'), Literal('+'), Literal('!'))), LeftAssoc(Call(Ref('wrap'), [Choice(Literal('/'), Literal('//'))])), LeftAssoc(Call(Ref('wrap'), [Choice(Literal('<<'), Literal('>>'), Literal('<<!'), Literal('!>>'))])), LeftAssoc(Call(Ref('wrap'), [Literal('|')])))),
        Rule('start', Right(Skip(Ref('Newline')), Alt(Ref('Def'), Ref('Sep'), allow_trailer=True))),
    ])


def _conv(node):
    if isinstance(node, (meta.Word, meta.Symbol)):
        return node.value

    if isinstance(node, meta.StringLiteral):
        return Literal(literal_eval(node.value))

    if isinstance(node, meta.RegexLiteral):
        # Strip the backticks.
        return Regex(node.value[1:-1])

    if isinstance(node, meta.Ref):
        return Ref(node.name)

    if isinstance(node, meta.ListLiteral):
        return Seq(*node.elements)

    if isinstance(node, meta.ArgList):
        return node

    if isinstance(node, meta.Postfix) and isinstance(node.operator, meta.ArgList):
        left = node.left
        classes = {
            'LeftAssoc': LeftAssoc,
            'OperatorPrecedence': OperatorPrecedence,
            'Postfix': Postfix,
            'Skip': Skip,
            'Some': Some,
        }
        if isinstance(left, Ref) and left.name in classes:
            return classes[left.name](*node.operator.args)
        else:
            return Call(left, node.operator.args)

    if isinstance(node, meta.Postfix):
        classes = {
            '?': Opt,
            '*': List,
            '+': Some,
            # '!': Commit,
        }
        if isinstance(node.operator, str) and node.operator in classes:
            return classes[node.operator](node.left)

    if isinstance(node, meta.Infix) and node.operator == '|':
        left, right = node.left, node.right
        left = list(left.exprs) if isinstance(left, Choice) else [left]
        right = list(right.exprs) if isinstance(right, Choice) else [right]
        return Choice(*left, *right)

    if isinstance(node, meta.Infix):
        classes = {
            '/': lambda a, b: Alt(a, b, allow_trailer=True),
            '//': lambda a, b: Alt(a, b, allow_trailer=False),
            '<<': Left,
            '>>': Right,
            # '<<!': lambda a, b: Left(a, Commit(b)),
            # '!>>': lambda a, b: Left(Commit(a), b),
        }
        return classes[node.operator](node.left, node.right)

    if isinstance(node, meta.KeywordArg):
        return KeywordArg(node.name, node.expr)

    if isinstance(node, meta.RuleDef):
        return Rule(node.name, node.expr)

    if isinstance(node, meta.ClassDef):
        return Class(node.name, node.fields)

    if isinstance(node, meta.TokenDef):
        is_ignored = node.is_ignored is not None
        node = node.child
        is_class = isinstance(node, Class)
        if is_class and not is_ignored:
            node.is_token = True
            return node
        elif is_class and is_ignored:
            return Token(node.name, node, is_ignored=True)
        else:
            return Token(node.name, node.expr, is_ignored=is_ignored)

    if isinstance(node, meta.TemplateDef):
        return Template(node.name, node.params, node.expr)

    if isinstance(node, str):
        return Literal(node)

    # TODO: Consider making an assertion here.
    return node


class Grammar:
    def __init__(self, description):
        self._description = description

        if isinstance(description, str):
            _setup()
            raw = meta.parse(description)
            cooked = meta.transform(raw, _conv)
        else:
            cooked = description

        self._nodes = _apply_templates(cooked)
        self._source_code = generate_source_code(self._nodes)
        self._module = _compile_source_code(self._source_code)

    def __getattr__(self, name):
        return getattr(self._module, name)


def _apply_templates(nodes):
    env = {x.name: x for x in nodes if isinstance(x, Template)}
    return [x._eval(env) for x in nodes]


def _compile_source_code(source_code, name='grammar'):
    code_object = compile(source_code, f'<{name}>', 'exec', optimize=2)
    module = types.ModuleType(name)
    exec(code_object, module.__dict__)
    return module
