# Runs the docker container and executes the command.
RUN := docker run --rm --name sourcer -v `pwd`:/workspace sourcer

# Generate the a python module to parse grammar specifications.
metasyntax:
	$(RUN) python generate_metasyntax.py

# Create a docker image with Python and our dev dependencies.
image: Dockerfile
	docker build -t sourcer .

# Remove random debris left around by python, pytest, and coverage.
clean:
	-rm -rf \
		__pycache__ \
		.coverage \
		.pytest_cache \
		**/__pycache__ \
		**/*.pyc \
		dist \
		htmlcov \
		MANIFEST

# Run the tests in a docker container.
test: clean image
	$(RUN) python -m pytest tests

# Run the tests, compute test coverage, and open the coverage report.
coverage: clean image
	$(RUN) /bin/bash -c "coverage run -m pytest tests \
		&& coverage report \
		&& coverage html"
	open "htmlcov/index.html"

# Run the code-formatter, but skip the generated python file.
black: image
	$(RUN) black sourcer -S --exclude 'meta.py'

# Upload the library to pypi.
upload:
	python setup.py sdist upload -r pypi
