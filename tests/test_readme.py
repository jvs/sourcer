import os
import re
import sys


def test_readme():
    project_home = os.path.dirname(os.path.dirname(__file__))
    path = os.path.join(project_home, 'README.rst')

    print('Running examples from', repr(path))
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
    for i, m in enumerate(pattern.finditer(content)):
        example = m.group(1)
        code = example.replace('\n    ', '\n')
        preview = code.strip()[0:70]
        print(f'  Running example {i + 1}')
        exec(code)
