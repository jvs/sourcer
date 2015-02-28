import inspect
from .expressions import *
from .tokens import *
from .structs import compile_struct


# A tuple of (object, int). The object is the parse tree, and the int value
# is the index of the last item consumed by the parser, plus one. (So it's
# the index of the next item that the parser should consume.)
ParseResult = namedtuple('ParseResult', 'value, pos')


ParseFailure = object()
ParseStep = namedtuple('ParseStep', 'parser, pos')


def compile(expression, is_text=True):
    attr = '_text_parser' if is_text else '_data_parser'
    is_operand = isinstance(expression, ParsingOperand)
    is_class = inspect.isclass(expression)
    is_cacheable = is_operand and not is_class
    if is_cacheable and hasattr(expression, attr):
        return getattr(expression, attr)

    compiler = _Compiler(is_text)
    parser = compiler.compile(expression)
    assert not isinstance(parser, ForwardingPointer)
    _replace_pointers(parser)

    if is_cacheable:
        setattr(expression, attr, parser)
    return parser


class ForwardingPointer(object): pass


def _replace_pointers(parser, visited=None):
    if visited is None:
        visited = set()
    elif id(parser) in visited:
        return
    visited.add(id(parser))

    if isinstance(parser, list):
        replacements = []
        for index, value in enumerate(parser):
            _replace_pointers(value, visited)
            if isinstance(value, ForwardingPointer):
                replacements.append((index, value.parser))
        for index, value in replacements:
            parser[index] = value

    if not hasattr(parser, '__dict__'):
        return

    for key, value in parser.__dict__.items():
        _replace_pointers(value, visited)
        if isinstance(value, ForwardingPointer):
            setattr(parser, key, value.parser)


class _Compiler(object):
    def __init__(self, is_text):
        self.is_text = is_text
        self.map = {}
        self.memo = {}

    def bind(self, value, function):
        key = (value, function)
        if key in self.memo:
            return self.memo[key]
        expression = function(value)
        parser = self.compile(expression)
        self.memo[key] = parser
        return parser

    def compile(self, node):
        if node in self.map:
            return self.map[node]
        ptr = ForwardingPointer()
        self.map[node] = ptr
        parser = self.compile_node(node)
        self.map[node] = parser
        ptr.parser = parser
        return parser

    def compile_node(self, node):
        is_cls = inspect.isclass(node)
        if is_cls and issubclass(node, Token):
            return self.compile_token(node)
        if is_cls and issubclass(node, Struct):
            return self.compile_struct(node)
        if not is_cls and not isinstance(node, ParsingOperand):
            return self.compile_default(node)
        suffix = node.__name__ if is_cls else node.__class__.__name__
        name = 'compile_%s' % suffix.lower()
        method = getattr(self, name, self.compile_default)
        return method(node)

    def compile_default(self, node):
        if isinstance(node, tuple):
            return self.compile_tuple(node)
        if isinstance(node, basestring):
            func = _text_prefix_eq if self.is_text else _token_content_eq
            return func(node)
        if hasattr(node, 'match'):
            func = _regex_text_parser if self.is_text else _regex_token_parser
            return func(node)
        delegate = Literal(node)
        return self.compile(delegate)

    def compile__alt(self, node):
        element, separator, allow_trailer = node
        rest = List(Right(separator, element))
        tail = Opt(separator) if allow_trailer else Return(None)
        triple = (element, rest, tail)
        delegate = Transform(Opt(triple), lambda t: [t[0]] + t[1] if t else [])
        return self.compile(delegate)

    def compile_and(self, node):
        delegate = Left(node.left, Expect(node.right))
        return self.compile(delegate)

    def compile_any(self, node):
        return _any_parser

    def compile__backtrack(self, node):
        return _backtrack_parser(node.count)

    def compile_bind(self, node):
        parser = self.compile(node.expression)
        return _BindParser(self.bind, parser, node.function)

    def compile_expect(self, node):
        parser = self.compile(node.expression)
        return _ExpectParser(parser)

    def compile_end(self, node):
        return _end_parser

    def compile_fail(self, node):
        return _fail_parser

    def compile_forwardref(self, node):
        expression = node.resolve()
        return self.compile(expression)

    def compile_left(self, node):
        left_parser = self.compile(node.left)
        right_parser = self.compile(node.right)
        return _LeftParser(left_parser, right_parser)

    def compile_list(self, node):
        parser = self.compile(node.element)
        return _ListParser(parser)

    def compile_literal(self, node):
        return _literal_parser(node.value)

    def compile_not(self, node):
        parser = self.compile(node.expression)
        return _NotParser(parser)

    def compile_opt(self, node):
        delegate = Or(node.expression, Return(None))
        return self.compile(delegate)

    def compile_or(self, node):
        parsers = []
        stack = [node]
        while stack:
            top = stack.pop()
            if isinstance(top, Or):
                stack.append(top.right)
                stack.append(top.left)
            else:
                parser = self.compile(top)
                parsers.append(parser)
        return _OrParser(parsers)

    def compile_require(self, node):
        parser = self.compile(node.expression)
        return _RequireParser(parser, node.predicate)

    def compile_return(self, node):
        return _return_parser(node.value)

    def compile_right(self, node):
        left_parser = self.compile(node.left)
        right_parser = self.compile(node.right)
        return _RightParser(left_parser, right_parser)

    def compile_some(self, node):
        delegate = Require(List(node.element), bool)
        return self.compile(delegate)

    def compile_start(self, node):
        return _start_parser

    def compile_struct(self, node):
        expression = compile_struct(node)
        return self.compile(expression)

    def compile_term(self, node):
        return self.compile(node.value)

    def compile_token(self, node):
        if not self.is_text:
            return _token_instance_parser(node)
        parser = self.compile(node._pattern)
        return _TokenParser(parser, node)

    def compile_transform(self, node):
        parser = self.compile(node.expression)
        return _TransformParser(parser, node.function)

    def compile_tuple(self, node):
        parsers = [self.compile(i) for i in node]
        return _SequenceParser(parsers)


def _any_parser(source, pos):
    yield (ParseFailure if pos >= len(source)
        else ParseResult(source[pos], pos + 1))


def _backtrack_parser(count):
    def parse(source, pos):
        dst = pos - count
        yield ParseFailure if dst < 0 else ParseResult(None, dst)
    return parse


def _end_parser(source, pos):
    at_end = (pos == len(source))
    yield ParseResult(None, pos) if at_end else ParseFailure


def _fail_parser(source, pos):
    yield ParseFailure


def _literal_parser(value):
    def parser(source, pos):
        is_match = (pos < len(source)) and source[pos] == value
        yield ParseResult(value, pos + 1) if is_match else ParseFailure
    return parser


def _return_parser(value):
    def parser(source, pos):
        yield ParseResult(value, pos)
    return parser


def _start_parser(source, pos):
    yield ParseResult(None, pos) if pos == 0 else ParseFailure


class _BindParser(object):
    def __init__(self, bind, parser, function):
        self.bind = bind
        self.parser = parser
        self.function = function

    def __call__(self, source, pos):
        step = yield ParseStep(self.parser, pos)
        if step is ParseFailure:
            yield ParseFailure
        parser = self.bind(step.value, self.function)
        ans = yield ParseStep(parser, step.pos)
        yield ans


class _ExpectParser(object):
    def __init__(self, parser):
        self.parser = parser

    def __call__(self, source, pos):
        ans = yield ParseStep(self.parser, pos)
        yield ans if ans is ParseFailure else ParseResult(ans.value, pos)


class _LeftParser(object):
    def __init__(self, left_parser, right_parser):
        self.left_parser = left_parser
        self.right_parser = right_parser

    def __call__(self, source, pos):
        ans = yield ParseStep(self.left_parser, pos)
        if ans is ParseFailure:
            yield ans
        skip = yield ParseStep(self.right_parser, ans.pos)
        yield skip if skip is ParseFailure else ParseResult(ans.value, skip.pos)


class _ListParser(object):
    def __init__(self, parser):
        self.parser = parser

    def __call__(self, source, pos):
        ans = []
        while True:
            elmt = yield ParseStep(self.parser, pos)
            if elmt is ParseFailure or pos == elmt.pos:
                break
            pos = elmt.pos
            ans.append(elmt.value)
        yield ParseResult(ans, pos)


class _NotParser(object):
    def __init__(self, parser):
        self.parser = parser

    def __call__(self, source, pos):
        ans = yield ParseStep(self.parser, pos)
        yield ParseResult(None, pos) if ans is ParseFailure else ParseFailure


class _OrParser(object):
    def __init__(self, parsers):
        self.parsers = parsers

    def __call__(self, source, pos):
        for parser in self.parsers:
            ans = yield ParseStep(parser, pos)
            if ans is not ParseFailure:
                yield ans
        yield ParseFailure


class _RequireParser(object):
    def __init__(self, parser, predicate):
        self.parser = parser
        self.predicate = predicate

    def __call__(self, source, pos):
        ans = yield ParseStep(self.parser, pos)
        failed = (ans is ParseFailure) or not self.predicate(ans.value)
        yield ParseFailure if failed else ans


class _RightParser(object):
    def __init__(self, left_parser, right_parser):
        self.left_parser = left_parser
        self.right_parser = right_parser

    def __call__(self, source, pos):
        skip = yield ParseStep(self.left_parser, pos)
        if skip is ParseFailure:
            yield skip
        ans = yield ParseStep(self.right_parser, skip.pos)
        yield ans


class _SequenceParser(object):
    def __init__(self, parsers):
        self.parsers = parsers

    def __call__(self, source, pos):
        ans = []
        for parser in self.parsers:
            elmt = yield ParseStep(parser, pos)
            if elmt is ParseFailure:
                yield ParseFailure
            ans.append(elmt.value)
            pos = elmt.pos
        yield ParseResult(tuple(ans), pos)


class _TransformParser(object):
    def __init__(self, parser, function):
        self.parser = parser
        self.function = function

    def __call__(self, source, pos):
        step = yield ParseStep(self.parser, pos)
        if step is ParseFailure:
            yield ParseFailure
        else:
            value = self.function(step.value)
            yield ParseResult(value, step.pos)


class _TokenParser(object):
    def __init__(self, parser, token_class):
        self.parser = parser
        self.token_class = token_class

    def __call__(self, source, pos):
        step = yield ParseStep(self.parser, pos)
        if step is ParseFailure:
            yield ParseFailure
        match = step.value
        ans = self.token_class(match.group(0))
        for k, v in match.groupdict().iteritems():
            setattr(ans, k, v)
        yield ParseResult(ans, step.pos)


def _token_instance_parser(token_class):
    def parser(source, pos):
        obj = source[pos] if pos < len(source) else None
        is_inst = isinstance(obj, token_class)
        yield ParseResult(obj, pos + 1) if is_inst else ParseFailure
    return parser


def _text_prefix_eq(string):
    count = len(string)
    def parser(source, pos):
        end = pos + count
        test = source[pos : end]
        yield ParseResult(string, end) if test == string else ParseFailure
    return parser


def _token_content_eq(string):
    def parser(source, pos):
        if pos >= len(source):
            yield ParseFailure
        is_match = string == getattr(source[pos], 'content')
        yield ParseResult(string, pos + 1) if is_match else ParseFailure
    return parser


def _regex_text_parser(regex):
    def parser(source, pos):
        match = regex.match(source, pos)
        yield ParseResult(match, match.end()) if match else ParseFailure
    return parser


def _regex_token_parser(regex):
    def parser(source, pos):
        if pos >= len(source):
            yield ParseFailure
        content = getattr(source[pos], 'content')
        match = regex.match(content)
        is_end = match and match.end() == len(source)
        yield ParseResult(match, pos + 1) if match else ParseFailure
    return parser
