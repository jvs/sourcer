from outsourcer import Code

from . import utils
from .apply import Apply
from .base import Expression
from .choice import Choice
from .constants import BREAK, POS, RESULT, STATUS
from .inline_python import PythonExpression
from .list import List
from .longest import Longest
from .sep import Sep
from .seq import Seq


class OperatorPrecedence(Expression):
    def __init__(self, operand, *operators):
        self.operand = operand
        self.operators = operators
        self.num_blocks = 3

    def __str__(self):
        items = [self.operand] + list(self.operators)
        lines = ',\n'.join(f'    {x}' for x in items)
        return f'OperatorPrecedence(\n{lines}\n)'

    def always_succeeds(self):
        return self.operand.always_succeeds()

    def can_partially_succeed(self):
        return not self.always_succeeds() and self.operand.can_partially_succeed()

    def complain(self):
        return 'Unexpected input'

    def _compile(self, out, flags):
        prefix, infix, postfix = [], [], []
        operand = [self.operand]

        associativities = [Prefix, LeftAssoc, RightAssoc, NonAssoc]

        for precedence, rule in enumerate(self.operators):
            operators = rule.operators
            precedence = precedence

            if isinstance(rule, Mixfix):
                operand.append(operators)
                continue

            if isinstance(rule, Postfix):
                tagger = f'lambda x: ({precedence}, x)'
                postfix.append(Apply(operators, PythonExpression(tagger)))
                continue

            associativity = associativities.index(rule.__class__)
            tagger = f'lambda x: ({precedence}, {associativity}, x)'
            tagged_operators = Apply(operators, PythonExpression(tagger))
            target = prefix if isinstance(rule, Prefix) else infix
            target.append(tagged_operators)

        def combine(exprs, suffix):
            if not exprs:
                return None
            if len(exprs) == 1:
                return exprs[0]
            else:
                result = Longest(*exprs)
                # Try sharing a program_id for now.
                result.program_id = self.program_id
                return result

        prefix = combine(prefix, 'prefix')
        postfix = combine(postfix, 'postfix')
        infix = combine(infix, 'infix')
        operand = combine(operand, 'operand')
        assert operand

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
            if prefix:
                with utils.repeat(out, flags, prefix, inner_checkpoint):
                    out += operator_stack.append(RESULT)

            if operand.can_partially_succeed():
                out += (inner_checkpoint << POS)

            with utils.if_fails(out, flags, operand):
                if operand.can_partially_succeed():
                    # If we have a result, then backtrack to the checkpoint.
                    with out.IF(operand_stack):
                        out += (POS << outer_checkpoint)
                out += BREAK

            # OK, we have an operand.
            out += operand_stack.append(RESULT)

            if postfix:
                with utils.repeat(out, flags, postfix, inner_checkpoint):
                    ops = operator_stack
                    with out.WHILE(Code(f'{ops} and {ops}[-1][0] < {RESULT[0]}')):
                        pop_operator()
                    out += Code('_operand') << operand_stack.pop()
                    out += operand_stack.append(Code(f'Postfix(_operand, {RESULT[1]})'))

            out += operator_marker << Code(f'len({operator_stack})')
            out += outer_checkpoint << POS

            if infix:
                with utils.if_fails(out, flags, infix):
                    if infix.can_partially_succeed():
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


class OperatorPrecedenceRule(Expression):
    def __init__(self, *operators):
        self.operators = operators[0] if len(operators) == 1 else Choice(*operators)

    def __str__(self):
        return f'{self.__class__.__name__}({self.operators})'


class LeftAssoc(OperatorPrecedenceRule): pass
class Mixfix(OperatorPrecedenceRule): pass
class NonAssoc(OperatorPrecedenceRule): pass
class Postfix(OperatorPrecedenceRule): pass
class Prefix(OperatorPrecedenceRule): pass
class RightAssoc(OperatorPrecedenceRule): pass
