.PHONY: test coverage lint

LINT_FILES := $(shell git ls-files -- '*.py' ':(exclude).claude/**')

lint:
	python3 -m pylint --errors-only --disable=no-member,not-callable $(LINT_FILES)

test:
	python3 -m pytest tests/unit/ -v

coverage:
	python3 -m pytest tests/unit/ --cov=. --cov-report=term-missing
