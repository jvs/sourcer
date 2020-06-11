clean:
	-rm -rf __pycache__ dist MANIFEST

install:
	python setup.py install

test: clean
	python3 -m tests.test_expressions
	python3 -m tests.test_metasyntax

upload:
	python setup.py sdist upload -r pypi
