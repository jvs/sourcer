from .apply import Apply
from .base import Expression
from .choice import Choice
from .inline_python import PythonExpression
from .list import List
from .sep import Sep
from .seq import Seq


def OperatorPrecedence(atom, *rules):
    if not rules:
        return atom

    prefix, infix, postfix = [], [], []
    operands = [atom]

    associativities = [Prefix, LeftAssoc, RightAssoc, NonAssoc]

    for precedence, rule in enumerate(rules):
        operators = rule.operators
        precedence = -precedence

        if isinstance(rule, Mixfix):
            operands.append(operators)
            continue

        if isinstance(rule, Postfix):
            tagger = f'lambda x: ({precedence}, x)'
            postfix.append(Apply(operators, PythonExpression(tagger)))
            continue

        assoc = associativities.index(rule.__class__)
        tagger = f'lambda x: ({precedence}, {assoc}, x)'
        tagged_operators = Apply(operators, PythonExpression(tagger))
        target = prefix if isinstance(rule, Prefix) else infix
        target.append(tagged_operators)

    def combine(parts, is_list=False):
        if parts:
            choice = parts[0] if len(parts) == 1 else Choice(*reversed(parts))
            return List(choice) if is_list else choice
        else:
            return PythonExpression('None')

    prefix = combine(prefix, is_list=True)
    postfix = combine(postfix, is_list=True)
    infix = combine(infix, is_list=False)
    operand = combine(operands, is_list=False)

    item = Seq(prefix, operand, postfix)
    stream = Sep(item, infix, discard_separators=False, allow_empty=False)
    reparse = PythonExpression('_apply_shunting_yard')
    return Apply(stream, reparse)


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
