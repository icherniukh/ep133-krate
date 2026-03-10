.PHONY: test coverage

test:
	python3 -m pytest tests/unit/ -v

coverage:
	python3 -m pytest tests/unit/ --cov=. --cov-report=term-missing
