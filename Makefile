.PHONY: install auth run test lint typecheck

install:
	python3 -m venv .venv
	.venv/bin/pip install -e ".[dev]"

auth:
	.venv/bin/python -m src.main --auth

run:
	.venv/bin/python -m src.main

test:
	.venv/bin/pytest tests/

lint:
	.venv/bin/ruff check src/ tests/

typecheck:
	.venv/bin/mypy src/
