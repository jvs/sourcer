from outsourcer import Code

from . import utils
from .base import Expression
from .constants import POS, RESULT, STATUS, TEXT
from .seq import Seq


class Class(Expression):
    has_params = True

    is_tagged = False
    is_commented = False

    num_blocks = 2

    def __init__(self, name, params, fields, is_ignored=False):
        self.name = name
        self.params = params
        self.fields = fields
        self.is_ignored = is_ignored
        self.extra_id = None

    def __str__(self):
        params = '' if self.params is None else f'({", ".join(self.params)})'
        fields = ''.join(f'    {x.name}: {x.expr}\n' for x in self.fields)
        return f'class {self.name}{params} {{\n{fields}}}'

    def always_succeeds(self):
        return all(x.expr.always_succeeds() for x in self.fields)

    def _compile(self, out):
        parse_func = Code(f'{utils.implementation_name(self.name)}')
        field_names = [x.name for x in self.fields]

        with out.global_section():
            with out.CLASS(self.name, 'Node'):
                self._compile_class_body(out, parse_func, field_names)

            with out.DEF(parse_func, [str(TEXT), str(POS)] + (self.params or [])):
                exprs = (x.expr for x in self.fields)
                seq = Seq(*exprs, names=field_names, constructor=self.name)
                seq.program_id = self.extra_id
                seq.compile(out)
                out.YIELD((STATUS, RESULT, POS))

    def _compile_class_body(self, out, parse_func, field_names):
        out.add_docstring(str(self))
        out += Code('_fields') << tuple(field_names)
        out.add_newline()

        with out.DEF('__init__', ['self'] + field_names):
            out += Code('Node.__init__(self)')
            for name in field_names:
                out += Code(f'self.{name} = {name}')

        with out.DEF('__repr__', ['self']):
            values = ', '.join(f'{x}={{self.{x}!r}}' for x in field_names)
            out.RETURN(Code(f"f'{self.name}({values})'"))

        out += Code('@staticmethod')
        if self.params:
            with out.DEF('parse', self.params):
                _closure, _ParseFunction = Code('_closure'), Code('_ParseFunction')
                args = tuple(Code(x) for x in self.params)
                out += _closure << _ParseFunction(parse_func, args, {})
                out.RETURN(Code(
                    'lambda text, pos=0, fullparse=True:'
                    ' _run(text, pos, _closure, fullparse)'
                ))
        else:
            with out.DEF('parse', ['text', 'pos=0', 'fullparse=True']):
                out.RETURN(Code(f'_run(text, pos, {parse_func}, fullparse)'))
