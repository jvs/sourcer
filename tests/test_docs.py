import glob
import os

import docutils


def test_docs():
    project_home = os.path.dirname(os.path.dirname(__file__))
    mds = os.path.join(project_home, 'docs', '**', '*.md')

    for md in glob.glob(mds, recursive=True):
        # For now, just skip metasyntax.md
        if md.endswith('metasyntax.md'):
            continue

        print('# Scanning', md)

        with open(md) as f:
            content = f.read()

        for python_code in find_test_cases(docutils.parse_doc(content)):
            preview = make_preview(python_code)
            print('# Running example:')
            print(preview)
            exec(python_code, {})


def find_test_cases(sections):
    buf = []
    for section in sections:
        if isinstance(section, str):
            continue

        if getattr(section, 'tag', '').upper() == 'HIDDEN TEST':
            buf.append(section.body)
            continue

        tag = section.comment.tag.upper()

        if tag in ['INPUT', 'OUTPUT', 'CONSOLE']:
            continue

        if tag == 'TEST':
            buf.append(section.python.body)
            continue

        if tag == 'SETUP':
            if buf:
                yield '\n'.join(buf)
            buf = [section.python.body]
            continue

    if buf:
        yield '\n'.join(buf)


def make_preview(python_code):
    preview = []
    for line in python_code.split('\n'):
        if not line.strip() or 'import' in line:
            continue
        preview.append(line)
        if len(preview) > 6:
            break
    return '\n'.join(preview)
