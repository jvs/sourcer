import os
import re
import setuptools


def long_description():
    try:
        with open('README.md') as f:
            return f.read()
    except:
        return ''


def install_requires():
    with open('requirements.txt') as f:
        return f.read().splitlines()


def version():
    with open(os.path.join('sourcer', '__init__.py')) as f:
        regex = re.compile('\\n__version__\\s*=\\s*[\'"]+([\\d\\.]+)[\'"]\n')
        return regex.search(f.read()).group(1)


setuptools.setup(
    name='sourcer',
    version=version(),
    author='jvs',
    author_email='vonseg@protonmail.com',
    url='https://github.com/jvs/sourcer',
    description='simple parsing library',
    long_description=long_description(),
    long_description_content_type='text/markdown',
    data_files=[('', ['README.md', 'requirements.txt', 'requirements-dev.txt'])],
    python_requires='>=3.6',
    install_requires=install_requires(),
    packages=['sourcer', 'sourcer.expressions'],
    classifiers=[
        'Development Status :: 2 - Pre-Alpha',
        'Topic :: Software Development :: Interpreters',
        'Topic :: Software Development :: Compilers',
        'License :: OSI Approved :: MIT License',
        'Programming Language :: Python',
    ],
    platforms='any',
    license='MIT License',
    keywords=['packrat', 'parser', 'peg'],
)
