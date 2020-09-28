#!/usr/bin/env python

from distutils.core import setup

def long_description():
    try:
        with open('README.rst') as f:
            return f.read()
    except:
        return ''

with open('requirements.txt') as f:
    requirements = f.read().splitlines()

setup(
    name = 'sourcer',
    version = '0.2.0',
    author = 'John K. Von Seggern',
    author_email = 'vonseg@protonmail.com',
    url = 'https://github.com/jvs/sourcer',
    description = 'simple parsing library',
    long_description = long_description(),
    install_requires = requirements,
    packages = ['sourcer'],
    classifiers = [
        'Development Status :: 2 - Pre-Alpha',
        'Topic :: Software Development :: Interpreters',
        'Topic :: Software Development :: Compilers',
        'License :: OSI Approved :: MIT License',
        'Programming Language :: Python',
    ],
    platforms = 'any',
    license = 'MIT License',
    keywords = ['packrat', 'parser', 'peg'],
)
