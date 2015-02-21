clean:
	-rm -f *.pyc sourcer/*.pyc tests/*.pyc MANIFEST
	-rm -rf dist

install:
	python setup.py install

test: clean
	python -m tests.test_examples
	python -m tests.test_sourcer
	python -m tests.test_excel

upload:
	python setup.py sdist upload -r pypi
