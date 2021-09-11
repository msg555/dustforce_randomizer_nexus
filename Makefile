.PHONY: format format-check pylint typecheck lint
PYTHON := python3

all: format lint test docs

format:
	$(PYTHON) -m black .

format-check:
	$(PYTHON) -m black --check .

pylint:
	$(PYTHON) -m pylint dfrandomizer

typecheck:
	$(PYTHON) -m mypy dfrandomizer

lint: format-check pylint typecheck
