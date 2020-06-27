RUN := docker run --rm --name sourcer -v `pwd`:/workspace sourcer

metasyntax:
	python3 generate_metasyntax.py

image: Dockerfile
	docker build -t sourcer .

container: clean image
	$(RUN) python -m tests.test_expressions

black: image
	$(RUN) black ./sourcer

clean:
	-rm -rf __pycache__ **/__pycache__ dist MANIFEST **/*.pyc .pytest_cache

test: clean image
	$(RUN) python -m pytest tests

coverage: clean image
	$(RUN) /bin/bash -c "coverage run -m pytest tests \
		&& coverage report \
		&& coverage html"
	open "htmlcov/index.html"

upload:
	python setup.py sdist upload -r pypi
