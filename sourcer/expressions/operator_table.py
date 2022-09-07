from outsourcer import Code

from . import utils
from .apply import Apply
from .base import Expression
from .choice import Choice
from .constants import BREAK, POS, RESULT, STATUS
from .inline_python import PythonExpression
from .longest import Longest


class OperatorTable(Expression):
    def __init__(self, operand_str, row_strs, prefixes, operands, postfixes, infixes):
        self.operand_str = operand_str
        self.row_strs = row_strs
        self.prefixes = prefixes
        self.operands = operands
        self.postfixes = postfixes
        self.infixes = infixes
        self.num_blocks = 4

    @classmethod
    def create(cls, operand, rows):
        prefixes, infixes, postfixes, row_strs = [], [], [], []
        operands = [operand]

        associativities = ['prefix', 'left', 'right', 'infix']

        for precedence, row in enumerate(rows):
            associativity, operators = row.associativity, row.operators

            if not operators:
                continue

            row_strs.append(f'    {associativity}: {", ".join(str(x) for x in operators)}')
            operators = operators[0] if len(operators) == 1 else Choice(*operators)

            if associativity == 'mixfix':
                operands.append(operators)
                continue

            if associativity == 'postfix':
                tagger = f'lambda x: ({precedence}, x)'
                postfixes.append(Apply(operators, PythonExpression(tagger)))
                continue

            assoc_id = associativities.index(associativity)
            tagger = f'lambda x: ({precedence}, {assoc_id}, x)'
            tagged_operators = Apply(operators, PythonExpression(tagger))
            target = prefixes if associativity == 'prefix' else infixes
            target.append(tagged_operators)

        def combine(exprs):
            if not exprs:
                return None
            elif len(exprs) == 1:
                return exprs[0]
            else:
                return Longest(*exprs)

        return cls(
            operand_str=str(operand),
            row_strs=row_strs,
            prefixes=combine(prefixes),
            operands=combine(operands),
            postfixes=combine(postfixes),
            infixes=combine(infixes),
        )

    def __str__(self):
        rows = '\n'.join(self.row_strs)
        return f'{self.operand_str} with operators {{\n{rows}\n}}'

    def always_succeeds(self):
        return self.operands.always_succeeds()

    def can_partially_succeed(self):
        return not self.always_succeeds() and self.operands.can_partially_succeed()

    def complain(self):
        return 'Unexpected input'

    def _compile(self, out, flags):
        outer_checkpoint = out.var('_outer_checkpoint', initializer=POS)
        inner_checkpoint = out.var('_inner_checkpoint')

        # Use the shunting yard algorithm to handle operator precedence and
        # associativity.
        operand_stack = out.var('_operand_stack', initializer=[])
        operator_stack = out.var('_operator_stack', initializer=[])
        operator_marker = out.var('_operator_marker', initializer=0)

        def pop_operator():
            out.append(Code('_, _is_infix, _operator') << operator_stack.pop())
            out.append(Code('_right') << operand_stack.pop())

            with out.IF(Code('_is_infix')):
                out.append(Code('_left') << operand_stack.pop())
                out.append(operand_stack.append(Code('Infix(_left, _operator, _right)')))

            with out.ELSE():
                out.append(operand_stack.append(Code('Prefix(_operator, _right)')))

        with out.WHILE(True):
            if self.prefixes:
                with utils.repeat(out, flags, self.prefixes, inner_checkpoint):
                    out += operator_stack.append(RESULT)

            if self.operands.can_partially_succeed():
                out += (inner_checkpoint << POS)

            with utils.if_fails(out, flags, self.operands):
                if self.operands.can_partially_succeed():
                    # If we have a result, then backtrack to the checkpoint.
                    with out.IF(operand_stack):
                        out += (POS << outer_checkpoint)
                out += BREAK

            # OK, we have an operand.
            out += operand_stack.append(RESULT)

            if self.postfixes:
                with utils.repeat(out, flags, self.postfixes, inner_checkpoint):
                    ops = operator_stack
                    with out.WHILE(Code(f'{ops} and {ops}[-1][0] < {RESULT[0]}')):
                        pop_operator()
                    out += Code('_operand') << operand_stack.pop()
                    out += operand_stack.append(Code(f'Postfix(_operand, {RESULT[1]})'))

            out += operator_marker << Code(f'len({operator_stack})')
            out += outer_checkpoint << POS

            if self.infixes:
                with utils.if_fails(out, flags, self.infixes):
                    if self.infixes.can_partially_succeed():
                        # If we have a result, then backtrack to the checkpoint.
                        with out.IF(operand_stack):
                            out += (POS << outer_checkpoint)
                    out += BREAK
            else:
                out += BREAK

            out += Code('_prec') << RESULT[0]

            with out.WHILE(operator_stack):
                out += Code('_top_prec, _top_assoc, _') << operator_stack[-1]

                with out.IF(Code(f'_top_prec < _prec or (_top_prec == _prec and _top_assoc == 1)')):
                    pop_operator()
                with out.ELIF(Code(f'_top_prec == _prec and _top_assoc == 3')):
                    out += (POS << outer_checkpoint)
                    out += BREAK
                with out.ELSE():
                    out += BREAK

            out += operator_marker << Code(f'len({operator_stack})')
            out += operator_stack.append(RESULT)

        with out.IF(operand_stack):
            # Outside the loop, pop any uncommitted operators.
            out += operator_stack << Code(f'{operator_stack}[:{operator_marker}]')
            with out.WHILE(operator_stack):
                pop_operator()

            out += RESULT << operand_stack[0]
            out += STATUS << True
