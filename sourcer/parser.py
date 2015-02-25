import inspect
from .terms import *
from .precedence import *


def parse(term, source):
    whole = Left(term, End)
    ans = parse_prefix(whole, source)
    return ans.value


def parse_prefix(term, source):
    parser = _Parser(source)
    return parser.run(term)


class _Parser(object):
    def __init__(self, source):
        self.source = source
        self.is_text = isinstance(source, basestring)
        self.memo = {}
        self.stack = []
        self.delegates = {}

    def run(self, term):
        ans = self._start(term, 0)
        while self.stack:
            top = self.stack[-1][-1]
            ans = top.send(ans)
            if isinstance(ans, ParseStep):
                ans = self._start(ans.term, ans.pos)
            else:
                key = self.stack.pop()[0]
                self.memo[key] = ans
        if ans is ParseFailure:
            raise ParseError()
        else:
            return ans

    def _start(self, term, pos):
        key = (term, pos)
        if key in self.memo:
            return self.memo[key]
        self.memo[key] = ParseFailure
        if term not in self.delegates:
            tmp = self._compile_term(term)
            self.delegates[term] = tmp.parse
        generator = self.delegates[term](self.source, pos)
        self.stack.append((key, generator))
        return None

    def _compile_term(self, term):
        while isinstance(term, ForwardRef):
            term = term.forward_term()
        if hasattr(term, 'parse'):
            return term
        if isinstance(term, tuple):
            return _Seq(term)
        if isinstance(term, basestring):
            return (_Substr if self.is_text else _TokenContent)(term)
        if inspect.isclass(term) and issubclass(term, Struct):
            return _compile_struct(term)
        if hasattr(term, 'match'):
            return (_MatchString if self.is_text else _MatchToken)(term)
        if term is None:
            return _Nothing
        else:
            return Literal(term)


def _compile_struct(term):
    fields = _struct_fields(term)
    if issubclass(term, (LeftAssoc, RightAssoc)):
        return _compile_assoc_struct(term, fields)
    else:
        return _compile_simple_struct(term, fields)


def _compile_assoc_struct(term, fields):
    first = fields[0][-1]
    middle = tuple(p[-1] for p in fields[1:-1])
    last = fields[-1][-1]
    def build(left, op, right):
        values = [left] + list(op) + [right]
        return _build_struct(term, fields, values)
    is_left = issubclass(term, LeftAssoc)
    cls = ReduceLeft if is_left else ReduceRight
    return cls(first, middle, last, build)


def _compile_simple_struct(term, fields):
    raw = tuple(i[1] for i in fields)
    build = lambda values: _build_struct(term, fields, values)
    return Transform(raw, build)


def _build_struct(term, fields, values):
    ans = term.__new__(term)
    for field, value in zip(fields, values):
        setattr(ans, field[0], value)
    return ans


def _struct_fields(cls):
    ans = []
    class collect_fields(cls):
        def __setattr__(self, name, value):
            ans.append((name, value))
            cls.__setattr__(self, name, value)
    collect_fields()
    return ans


class _MatchToken(object):
    def __init__(self, regex):
        self.regex = regex

    def parse(self, source, pos):
        yield ParseFailure
        if pos >= len(source):
            yield ParseFailure
        content = getattr(source[pos], 'content')
        match = self.regex.match(content)
        is_end = match and match.end() == len(source)
        yield ParseResult(match, pos + 1) if match else ParseFailure


class _MatchString(object):
    def __init__(self, regex):
        self.regex = regex

    def parse(self, source, pos):
        match = self.regex.match(source, pos)
        yield ParseResult(match, match.end()) if match else ParseFailure


class _Nothing(object):
    @staticmethod
    def parse(source, pos):
        yield ParseResult(None, pos)


class _Seq(object):
    def __init__(self, terms):
        self.terms = terms

    def parse(self, source, pos):
        ans = []
        for term in self.terms:
            next = yield ParseStep(term, pos)
            if next is ParseFailure:
                yield ParseFailure
            ans.append(next.value)
            pos = next.pos
        yield ParseResult(tuple(ans), pos)


class _Substr(object):
    def __init__(self, string):
        self.string = string

    def parse(self, source, pos):
        ans = self.string
        end = pos + len(ans)
        test = source[pos : end]
        yield ParseResult(ans, end) if test == ans else ParseFailure


class _TokenContent(object):
    def __init__(self, string):
        self.string = string

    def parse(self, source, pos):
        if pos >= len(source):
            yield ParseFailure
        ans = self.string
        is_match = ans == getattr(source[pos], 'content')
        yield ParseResult(ans, pos + 1) if is_match else ParseFailure
