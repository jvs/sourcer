PYTHON := .venv/bin/python

test: venv sourcer/parser.py
	$(PYTHON) -m pytest -vv -s tests

sourcer/parser.py: venv grammar.txt generate_parser.py
	$(PYTHON) generate_parser.py

venv: .venv/bin/activate

.venv/bin/activate: requirements.txt requirements-dev.txt
	test -d .venv || python3 -m venv .venv
	.venv/bin/pip install --upgrade pip
	.venv/bin/pip install -r requirements.txt
	.venv/bin/pip install -r requirements-dev.txt
	touch .venv/bin/activate

# Remove random debris left around by python, pytest, and coverage.
clean:
	@echo "Removing generated files."
	@rm -rf \
		__pycache__ \
		.coverage \
		.pytest_cache \
		**/__pycache__ \
		**/*.pyc \
		docs/_build/* \
		dist \
		htmlcov \
		MANIFEST \
		*.egg-info

# Run the tests, compute test coverage, and open the coverage report.
coverage: clean venv sourcer/parser.py
	.venv/bin/coverage run -m pytest tests
	.venv/bin/coverage report
	.venv/bin/coverage html
	open "htmlcov/index.html"

# Build the documentation.
docs: venv sourcer/parser.py
	$(PYTHON) -m exemplary --paths "**/*.md" --render
	$(MAKE) -C docs html

# Run the code-formatter, but skip the generated python file.
black: venv
	.venv/bin/black sourcer -S --exclude 'parser.py'

# How to publish a release:
# - Update __version__ in sourcer/__init__.py.
# - Commit / merge to "main" branch.
# - Run:
#   - make tag
#   - make test_upload
#   - make real_upload

tag: clean
	$(eval VERSION=$(shell sed -n -E \
		"s/^__version__ = [\'\"]([^\'\"]+)[\'\"]$$/\1/p" \
		sourcer/__init__.py))
	@echo Tagging version $(VERSION)
	git tag -a $(VERSION) -m "Version $(VERSION)"
	git push origin $(VERSION)

# Build the distributeion.
dist:
	rm -rf dist/
	$(PYTHON) setup.py sdist
	.venv/bin/twine check dist/*

# Upload the library to pypitest.
test_upload: dist
	.venv/bin/twine upload --repository pypitest dist/*

# Upload the library to pypi.
real_upload: dist
	.venv/bin/twine upload --repository pypi dist/*

.PHONY: clean docs test coverage black dist test_upload real_upload
