import re
import sys


def run_readme_examples(path):
    print 'Running examples from', path
    with open(path) as f:
        content = f.read()
    pattern = re.compile(r'''
        \.\.      # leading '..'
        \s*       # optional spaces
        code      # magic keyword
        \:\:      # magic marker
        \s+       # some spaces
        python    # language name
        \n        # newline

        # Each line is indented with four spaces.
        (((\ {4}.*)?\n)+)
        ''',
        re.IGNORECASE | re.VERBOSE
    )
    for m in pattern.finditer(content):
        example = m.group(1)
        code = example.replace('\n    ', '\n')
        preview = code.strip()[0:70]
        print '  running', repr(preview)
        exec code in {}


if __name__ == '__main__':
    run_readme_examples(sys.argv[1])
