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
		docs/_build/* \
		dist \
		htmlcov \
		MANIFEST

# Run the tests in a docker container.
test: clean image
	$(RUN) python -m pytest -v -s tests

# Run the tests, compute test coverage, and open the coverage report.
coverage: clean image
	$(RUN) /bin/bash -c "coverage run -m pytest tests \
		&& coverage report \
		&& coverage html"
	open "htmlcov/index.html"

# Build the documentation.
docs:
	$(RUN) python render_output_for_examples.py
	$(MAKE) -C docs html

# Run the code-formatter, but skip the generated python file.
black: image
	$(RUN) black sourcer -S --exclude 'meta.py'

# You can use a file called "wip.py" to run experiments.
wip:
	$(RUN) python wip.py

# Build the distributeion.
dist:
	rm -rf dist/
	python3 setup.py sdist
	twine check dist/*

# Upload the library to pypitest.
test_upload: dist
	twine upload --repository pypitest dist/*

# Upload the library to pypi.
real_upload: dist
	twine upload --repository pypi dist/*

.PHONY: clean docs test coverage black wip dist test_upload real_upload
