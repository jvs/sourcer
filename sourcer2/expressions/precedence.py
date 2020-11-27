from .base import Expression
from .choice import Choice


class OperatorPrecedence(Expression):
    def __init__(self, atom, *rules):
        self.atom = atom
        self.rules = rules
        self.num_blocks = (rules[-1] if rules else atom).num_blocks

    def __str__(self):
        rules = [self.atom] + list(self.rules)
        lines = ',\n'.join(f'    {x}' for x in rules)
        return f'OperatorPrecedence(\n{lines}\n)'

    def _compile(self, pb):
        prev = self.atom
        for rule in self.rules:
            rule.operand = prev
            prev = rule
        prev.compile(pb)


class OperatorPrecedenceRule(Expression):
    def __init__(self, *operators):
        self.operators = operators[0] if len(operators) == 1 else Choice(*operators)
        self.operand = None

    def __str__(self):
        return f'{self.__class__.__name__}({self.operators})'
