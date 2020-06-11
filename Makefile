clean:
	-rm -rf __pycache__ dist MANIFEST

install:
	python setup.py install

test: clean
	python3 -m tests.test_expressions
	python3 -m tests.test_metasyntax
	python3 -m tests.test_excel

upload:
	python setup.py sdist upload -r pypi
