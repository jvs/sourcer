clean:
	-rm -f *.pyc sourcer/*.pyc tests/*.pyc MANIFEST
	-rm -rf dist

clean2: clean
	-rm -rf __pycache__

install:
	python setup.py install

test: clean
	python -m tests.test_readme README.rst
	python -m tests.test_examples
	python -m tests.test_sourcer
	python -m tests.test_excel

test2: clean2
	python3 -m tests.test_expressions2
	python3 -m tests.test_metasyntax

upload:
	python setup.py sdist upload -r pypi
