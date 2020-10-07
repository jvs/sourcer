import setuptools

def long_description():
    try:
        with open('README.md') as f:
            return f.read()
    except:
        return ''


setuptools.setup(
    name = 'sourcer',
    version = '0.3.6',
    author = 'John K. Von Seggern',
    author_email = 'vonseg@protonmail.com',
    url = 'https://github.com/jvs/sourcer',
    description = 'simple parsing library',
    long_description = long_description(),
    long_description_content_type = 'text/markdown',
    python_requires = '>=3.6',
    install_requires = [],
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
