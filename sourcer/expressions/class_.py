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

    def __init__(self, name, params, members, is_ignored=False):
        self.name = name
        self.params = params
        self.members = members
        self.is_ignored = is_ignored
        self.extra_id = None

    def __str__(self):
        params = '' if self.params is None else f'({", ".join(self.params)})'
        lines = []
        for member in self.members:
            mod = 'let ' if member.is_omitted else ''
            lines.append(f'    {mod}{member.name}: {member.expr}\n')
        return f'class {self.name}{params} {{\n{"".join(lines)}}}'

    def always_succeeds(self):
        return all(x.expr.always_succeeds() for x in self.members)

    def _compile(self, out, flags):
        parse_func = utils.implementation_name(self.name)
        all_names = [x.name for x in self.members]
        field_names = [x.name for x in self.members if not x.is_omitted]
        class_attrs = []

        for member in self.members:
            if member.is_omitted:
                const_value = member.expr.constantize()
                if const_value is not None:
                    class_attrs.append((member.name, const_value))

        with out.global_section():
            with out.CLASS(self.name, 'Node'):
                self._compile_class_body(
                    out, flags, parse_func, field_names, class_attrs
                )

            extra_params = ['_ctx'] if flags.uses_context else []
            parse_params = extra_params + [str(TEXT), str(POS)]

            with out.DEF(parse_func, parse_params + (self.params or [])):
                exprs = (x.expr for x in self.members)
                seq = Seq(
                    *exprs,
                    names=all_names,
                    constructor=self.name,
                    constructor_args=field_names,
                )
                seq.program_id = self.extra_id
                seq.compile(out, flags)
                out.YIELD((STATUS, RESULT, POS))

    def _compile_class_body(self, out, flags, parse_func, field_names, class_attrs):
        out.add_docstring(str(self))
        out += Code('_fields') << tuple(field_names)
        out.add_newline()

        if flags.uses_context:
            parse_func = Code(f'_ctx.{parse_func}')
        else:
            parse_func = Code(parse_func)

        if class_attrs:
            for name, value in class_attrs:
                out += Code(f'{name} = {value}')
            out.add_newline()

        with out.DEF('__init__', ['self'] + field_names):
            out += Code('Node.__init__(self)')
            for name in field_names:
                out += Code(f'self.{name} = {name}')

        with out.DEF('__repr__', ['self']):
            values = ', '.join(f'{x}={{self.{x}!r}}' for x in field_names)
            out.RETURN(Code(f"f'{self.name}({values})'"))

        ctx = '_ctx, ' if flags.uses_context else ''

        out += Code('@staticmethod')
        if self.params:
            with out.DEF('parse', self.params):
                _closure, _ParseFunction = Code('_closure'), Code('_ParseFunction')
                args = tuple(Code(x) for x in self.params)
                out += _closure << _ParseFunction(parse_func, args, {})
                out.RETURN(Code(
                    f'lambda {ctx}text, pos=0, fullparse=True:'
                    f' _run({ctx}text, pos, _closure, fullparse)'
                ))
        else:
            with out.DEF('parse', ['text', 'pos=0', 'fullparse=True']):
                out.RETURN(Code(f'_run({ctx}text, pos, {parse_func}, fullparse)'))
