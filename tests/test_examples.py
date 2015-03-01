'''Search all our doc comments for "Example" blocks and try executing them.'''
import re
import sourcer.expressions


def run_examples(package):
    pattern = re.compile(r'''
        (\s*)      # initial indent
        Example    # magic keyword
        ([^\n]*)   # optional description
        \:\:       # magic marker

        # Each line of the example is indented
        # by four additional spaces:
        (\n((\1\ \ \ \ .*)?\n)+)
        ''',
        re.IGNORECASE | re.VERBOSE
    )

    for k, v in package.__dict__.iteritems():
        if k.startswith('__') and k.endswith('__'):
            continue
        doc = getattr(v, '__doc__') or ''
        for m in pattern.finditer(doc):
            indent = '\n    ' + m.group(1)
            body = m.group(3)
            example = body.replace(indent, '\n')
            print '  Running', k, 'example', m.group(2).strip()
            exec example in {}


if __name__ == '__main__':
    run_examples(sourcer.expressions)
