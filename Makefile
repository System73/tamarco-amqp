.PHONY: clean clean-test clean-pyc clean-build help
.DEFAULT_GOAL := help

help: Makefile
	@echo
	@echo " Choose a command run in "$(PROJECT_NAME)":"
	@echo
	@sed -n 's/^##//p' $< | column -t -s ':' |  sed -e 's/^/ /'
	@echo

## clean: remove all build, test, coverage and Python artifacts
clean: clean-build clean-pyc clean-test

## clean-build: remove build artifacts
clean-build:
	rm -fr build/
	rm -fr dist/
	rm -fr .eggs/
	find . -name '*.egg-info' -exec rm -fr {} +
	find . -name '*.egg' -exec rm -f {} +

 ## clean-pyc: remove Python file artifacts
clean-pyc:
	find . -name '*.pyc' -exec rm -f {} +
	find . -name '*.pyo' -exec rm -f {} +
	find . -name '*~' -exec rm -f {} +
	find . -name '__pycache__' -exec rm -fr {} +

 ## clean-test: remove tes: and coverage artifacts
clean-test:
	rm -fr .tox/
	rm -f .coverage
	rm -fr htmlcov/
	rm -fr reports/
	rm -fr .pytest_cache
	rm -fr .cache
	rm -fr .coverage.*

## setup-test: setup the current environment to run the tests
setup-test: clean
	mkdir -p reports

## test: run the tests
test: setup-test
	pytest -vv --junit-xml=reports/test.xml

## test-coverage: run the tests with coverage
test-coverage: setup-test
	coverage run -m pytest tests -vv --junit-xml=reports/test.xml
	coverage combine && coverage xml && coverage html

## linters: run flake 8
linters:
	python -m flake8 . && python -m black . --check

## dist: build the package
dist: clean
	python setup.py sdist
	ls -l dist

## install: install the package to the active Python's site-packages
install: clean
	python setup.py install

## format-code: formats the code with a code formatter
format-code:
	black .
