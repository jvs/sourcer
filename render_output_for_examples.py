import glob
import io
import os
import sys

from sourcer import Grammar
from tests import docutils


def run():
    project_home = os.path.dirname(__file__)
    mds = os.path.join(project_home, 'docs', '**', '*.md')

    for md in glob.glob(mds, recursive=True):
        # For now, just skip metasyntax.md
        if md.endswith('metasyntax.md'):
            continue

        print('# Scanning', md)

        with open(md) as f:
            content = f.read()

        parsed = docutils.parse_doc(content)
        outputs = []

        for python_code in find_python_examples(parsed):
            print('# Running:')
            lines = [x for x in python_code.split('\n') if x.strip()]
            print('\n'.join(lines[:7]))
            print('...')
            buf = io.StringIO()
            old_stdout = sys.stdout
            sys.stdout = buf
            try:
                exec(python_code, {})
            finally:
                sys.stdout = old_stdout

            outputs.extend(g.parse(buf.getvalue()))

        outputs.reverse()
        get_old_content = lambda x: content[x.start.index : x.end.index + 1]
        new_content = []
        for section in parsed:
            if isinstance(section, str):
                new_content.append(section)
                continue
            if isinstance(section, docutils.g.HiddenSection):
                new_content.append(get_old_content(section._position_info))
                continue
            tag = section.comment.tag.upper()
            if tag in ['SETUP', 'INPUT', 'TEST']:
                new_content.append(get_old_content(section._position_info))
                continue
            else:
                repl = outputs.pop()
                assert repl.open == repl.close
                assert repl.open == (tag == 'CONSOLE')
                new_content.append(f'<!-- {tag} -->\n```python\n')
                new_content.append(repl.body.strip())
                new_content.append('\n```')
                continue

        new_content = ''.join(new_content)
        if new_content != content:
            print('# Updating', md)
            with open(md, 'w') as f:
                f.write(new_content)


g = Grammar(r'''
    start = Noise? >> List(Output << Noise?)
    Noise = /([^\~]|\n|~[^~])+/
    class Output {
        open: /~~~~~ BEGIN( CONSOLE)? OUTPUT ~~~~~\n/ |> `lambda x: 'CONSOLE' in x`
        body: /(.|\n)*?(?=~~~~~)/
        close: /~~~~~ END( CONSOLE)?\ OUTPUT ~~~~~/ |> `lambda x: 'CONSOLE' in x`
    }
''')


def find_python_examples(sections):
    buf = []
    for section in sections:
        if isinstance(section, str):
            continue

        if getattr(section, 'tag', '').upper() == 'HIDDEN TEST':
            continue

        tag = section.comment.tag.upper()


        if tag == 'TEST':
            buf.append(section.python.body)
            continue

        if tag == 'INPUT':
            buf.append("\nprint('~~~~~ BEGIN OUTPUT ~~~~~')\n")
            buf.append(section.python.body)
            buf.append("print('~~~~~ END OUTPUT ~~~~~')\n")
            continue

        if tag == 'OUTPUT':
            continue

        if tag == 'CONSOLE':
            buf.append("\nprint('~~~~~ BEGIN CONSOLE OUTPUT ~~~~~')\n")
            for line in section.python.body.split('\n'):
                if line.startswith('>>> '):
                    expr = line[len('>>> '):]
                    line = f'print({line!r})\nprint(repr({expr}))\nprint()\n'
                    buf.append(line)
            buf.append("print('~~~~~ END CONSOLE OUTPUT ~~~~~')\n")
            continue

        if tag == 'SETUP':
            if buf:
                yield '\n'.join(buf)
            buf = [section.python.body]
            continue

    if buf:
        yield '\n'.join(buf)


if __name__ == '__main__':
    run()
