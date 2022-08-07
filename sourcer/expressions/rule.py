from outsourcer import Code

from . import utils
from .base import Expression
from .constants import POS, RESULT, STATUS, TEXT


class Rule(Expression):
    has_params = True

    is_tagged = False
    is_commented = False

    num_blocks = 1

    def __init__(self, name, params, expr, is_ignored=False, is_omitted=False):
        self.name = name
        self.params = params
        self.expr = expr
        self.is_ignored = is_ignored
        self.is_omitted = is_omitted

    def __str__(self):
        params = '' if self.params is None else f'({", ".join(self.params)})'
        return f'{self.name}{params} = {self.expr}'

    def _compile(self, out, flags):
        extra_params = ['_ctx'] if flags.uses_context else []
        params = extra_params + [str(TEXT), str(POS)] + (self.params or [])
        impl_name = utils.implementation_name(self.name)
        entry_name = f'_parse_{self.name}'

        definition = str(self)
        if '"""' in definition:
            definition = definition.replace('"""', '\\"\\"\\"')

        with out.global_section():
            with out.DEF(impl_name, params):
                out.add_comment(f'Rule {self.name!r}')
                self.expr.compile(out, flags)
                out.YIELD((STATUS, RESULT, POS))

            with out.DEF(entry_name, ['text', 'pos=0', 'fullparse=True']):
                ctx = '_ctx, ' if flags.uses_context else ''
                out.RETURN(Code(f'_run({ctx}text, pos, {impl_name}, fullparse)'))

            out += Code(f'{self.name} = Rule({self.name!r}, {entry_name}, """')
            out.extend(Code('    ', x) for x in definition.split('\n'))
            out += Code('""")')
