from sourcer_dev import *


# rule1 = Rule('foobarbaz', Seq('foo', ', ', 'bar', ', ', 'baz'))
# prog1 = compile_rule(rule1)
# result1 = prog1.run('foo, bar, baz')
# print(result1)


start = Rule('start', Choice(Ref('foo'), Ref('bar')))
foo = Rule('foo', Seq('foo', 'bar'))
bar = Rule('bar', Seq('bar', 'foo'))
mod = compile_rules(start.name, [start, foo, bar])
result = mod.run('barfoo')
print(result)
