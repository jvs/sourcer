import glob
import os
import re


def test_docs():
    project_home = os.path.dirname(os.path.dirname(__file__))
    mds = os.path.join(project_home, 'docs', '**', '*.md')
    pattern = re.compile(r'```python\n((.|\n)+?)```')

    for md in glob.glob(mds, recursive=True):
        print('# Scanning', md)

        with open(md) as f:
            content = f.read()

        sections = []
        for m in pattern.finditer(content):
            section = m.group(1).strip()
            if not sections:
                sections.append(section)
                continue
            if 'Grammar(' in section:
                sections.append(section)
            else:
                prev = sections.pop()
                sections.append(f'{prev}\n\n{section}')

        for section in sections:
            preview = []
            for line in section.split('\n'):
                if not line.strip():
                    continue
                preview.append(line)
                if len(preview) > 4:
                    break

            print('# Running example:')
            print('\n'.join(preview))
            print('...')
            exec(section, {})
