from ast import literal_eval
import re

from .expressions2 import *


class Grammar:
    def __init__(self, grammar):
        self.grammar = grammar
        self._env, self.parser = _create_parser(grammar)

    def __getattr__(self, name):
        if name in self._env:
            return self._env[name]
        else:
            raise AttributeError(f'Grammar has no value {name!r}.')

    def parse(self, text):
        return self.parser.parse(text)


def _create_parser(grammar):
    tree = metaparser.parse(grammar)

    env = {
        'Any': Any,
        'End': End,
        'Expect': Expect,
        'ExpectNot': ExpectNot,
        'Literal': Literal,
        'Skip': Skip,
        'Token': TokenClass,
    }

    def lazy(name):
        def tmp():
            print(f'looking up {name!r}')
            print(f'  found: {env[name]!r}')
            return env[name]
        return Lazy(tmp)
        return Lazy(lambda: env[name])

    for stmt in tree:
        env[stmt.name] = lazy(stmt.name)

    for stmt in tree:
        stmt.evaluate(env)

    if 'start' not in env:
        raise Exception('Expected "start" definition.')

    parser = Parser(
        start=env['start'],
        tokens=[v for v in env.values()
            if isinstance(v, type) and issubclass(v, Token)],
    )
    return env, parser


Whitespace = TokenPattern(r'[ \t]+', is_dropped=True)
Word = TokenPattern(r'[_a-zA-Z][_a-zA-Z0-9]*')
Symbol = TokenPattern(r'<<|>>|\/\/|[=;,:\|\/\*\+\?\!\(\)\[\]\{\}]')
StringLiteral = TokenPattern(
    r'("([^"\\]|\\.)*")|'
    r"('([^'\\]|\\.)*')|"
    r'("""([^\\]|\\.)*?""")|'
    r"('''([^\\]|\\.)*?''')"
)
RegexLiteral = TokenPattern(r'`([^`\\]|\\.)*`')
Newline = TokenPattern(r'[\r\n][\s]*')
Comment = TokenPattern(r'#[^\r\n]*', is_dropped=True)

def transform_tokens(tokens):
    result = []
    depth = 0
    for token in tokens:
        # Drop newline tokens that appear within parentheses.
        if token.value in '([':
            depth += 1
        elif token.value in '])':
            depth -= 1
        elif depth > 0 and isinstance(token, Newline):
            continue
        result.append(token)
    return result

# A forward reference to the MetaExpr definition.
Ex = Lazy(lambda: MetaExpr)

# Statement separator.
Sep = Some(Newline | ';')

Name = Word * (lambda w: w.value)


def _wrap(x):
    return Skip(Newline) >> x << Skip(Newline)


class Let(Struct):
    name = Name << Commit(Choice('=', ':'))
    value = Ex

    def evaluate(self, env):
        env[self.name] = _evaluate(env, self.value)


class ClassDef(Struct):
    name = Commit('class') >> Name
    fields = _wrap('{') >> (Let / Sep) << '}'

    def evaluate(self, env):
        class cls(Struct): pass
        cls.__name__ = self.name
        for field in self.fields:
            setattr(cls, field.name, _evaluate(env, field.value))
        env[self.name] = cls


class ListLiteral(Struct):
    elements = Commit('[') >> (Ex / ',') << ']'

    def evaluate(self, env):
        return Seq(*[_evaluate(env, x) for x in self.elements])


Atom = Choice(
    Commit('(') >> Ex << ')',
    Word,
    StringLiteral,
    RegexLiteral,
    ListLiteral,
)


class ArgList(Struct):
    args = Commit('(') >> (Ex / ',') << ')'

    def evaluate(self, env):
        return [_evaluate(env, x) for x in args]


MetaExpr = OperatorPrecedence(
    Atom,
    Postfix(ArgList),
    Postfix(Choice('?', '*', '+', '!')),
    LeftAssoc(_wrap(Choice('/', '//'))),
    LeftAssoc(_wrap(Choice('<<', '>>'))),
    LeftAssoc(_wrap('|')),
)

metaparser = Parser(
    start=Skip(Newline) >> ((ClassDef | Let) / Sep) << End,
    tokens=[
        Whitespace,
        Word,
        Symbol,
        StringLiteral,
        RegexLiteral,
        Newline,
        Comment,
    ],
    transform_tokens=transform_tokens,
)


def _evaluate(env, obj):
    if hasattr(obj, 'evaluate'):
        return obj.evaluate(env)

    if isinstance(obj, Word):
        name = obj.value
        if name in env:
            return env[name]
        else:
            raise Exception(f'Undefined: {name!r}')

    if isinstance(obj, StringLiteral):
        return literal_eval(obj.value)

    if isinstance(obj, RegexLiteral):
        return re.compile(obj.value[1:-1])

    operators = {
        '?': Opt,
        '*': List,
        '+': Some,
        '!': Commit,
        '/': lambda a, b: Alt(a, b, allow_trailer=True),
        '//': lambda a, b: Alt(a, b, allow_trailer=False),
        '<<': Left,
        '>>': Right,
        '|': Choice,
    }

    assert hasattr(obj, 'operator')
    operator = getattr(obj.operator, 'value', None)

    if isinstance(obj, InfixOp) and operator in operators:
        left = _evaluate(env, obj.left)
        right = _evaluate(env, obj.right)
        return operators[operator](left, right)

    if isinstance(obj, PostfixOp) and operator in operators:
        return operators[operator](_evaluate(env, obj.left))

    if isinstance(obj, PostfixOp):
        func = _evaluate(env, obj.left)
        if not callable(func):
            raise Exception(f'Not a callable function: {obj.left!r}')
        return func(*_evaluate(env, obj.operator))

    raise Exception(f'Unexpected expression: {obj!r}')
