RUN := docker run --rm --name sourcer -v `pwd`:/workspace sourcer

image: Dockerfile
	docker build -t sourcer .

container: clean image
	$(RUN) python -m tests.test_expressions

black: image
	$(RUN) black ./sourcer

clean:
	-rm -rf **/__pycache__ dist MANIFEST **/*.pyc

test: clean image
	$(RUN) python -m pytest tests

upload:
	python setup.py sdist upload -r pypi
