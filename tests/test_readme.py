import os
import re


def test_readme():
    project_home = os.path.dirname(os.path.dirname(__file__))
    path = os.path.join(project_home, 'README.md')

    print('Running examples from', repr(path))
    with open(path) as f:
        content = f.read()

    pattern = re.compile(r'```python\n((.|\n)+?)```')

    for i, m in enumerate(pattern.finditer(content)):
        code = m.group(1).strip()
        print(f'#  Running example {i + 1}')

        preview = []
        for line in code.split('\n'):
            if not line.strip():
                continue
            if not preview and 'Grammar(' not in line:
                continue
            preview.append(line)
            if len(preview) > 4:
                break

        print('\n'.join(preview))
        print()
        exec(code)
