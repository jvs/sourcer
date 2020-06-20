# from sourcer import *

# g = Grammar(r'''
#     start = (Line / ";") << End
#     Line = [Word!, Word, Word]
#     recover Line = SkipTo(";")

#     token Word = `[_a-zA-Z][_a-zA-Z0-9]*`
#     token Symbol = ";"
#     ignored token Space = `\s+`
# ''')

# try:
#     print(g.parse('foo bar  ; zim zam zum;'))
# except ParseError as err:
#     print('\ncaught parse error!')
#     print('result:')
#     print(err.result)
#     print('\nerrors:')
#     print(err.errors)


from sourcer.expressions3 import *

foo = Rule('foo', Choice('foo', 'bar', 'baz', Ref('foo')))
out = ProgramBuilder()
result = out.run([foo])

print(result)
