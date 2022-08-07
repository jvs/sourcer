from outsourcer import Code

from . import utils
from .base import Expression
from .constants import BREAK, POS, RESULT


class Seq(Expression):
    is_commented = False
    num_blocks = 2

    def __init__(self, *exprs, names=None, constructor=None, constructor_args=None):
        if isinstance(constructor, type):
            constructor = constructor.__name__
        self.exprs = exprs

        if names is not None:
            if len(names) != len(exprs):
                raise Exception('Expected same number of expressions and names.')
            self.names = names
        else:
            self.names = [None] * len(exprs)

        self.needs_parse_info = constructor is not None
        self.constructor = None if constructor is None else Code(constructor)
        self.constructor_args = constructor_args

    def __str__(self):
        return f'[{", ".join(str(x) for x in self.exprs)}]'

    def _compile(self, out, flags):
        if self.needs_parse_info:
            start_pos = out.var('start_pos', POS)

        cargs = self.constructor_args
        which = None if cargs is None else set(cargs)

        with utils.breakable(out):
            items = []
            for name, expr in zip(self.names, self.exprs):
                with utils.if_fails(out, flags, expr):
                    out += BREAK

                item = out.var('item') if name is None else Code(name)
                out += item << RESULT

                if which is None or name in which:
                    items.append(item)

            result = items if self.constructor is None else self.constructor(*items)
            out += RESULT << result

            if self.needs_parse_info:
                out += RESULT._metadata.position_info << (start_pos, POS)
