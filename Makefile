.DEFAULT_GOAL := help

.PHONY: help check lint format typecheck imports test

help:
	@echo "Usage: make <target>"
	@echo ""
	@echo "Checks"
	@echo "  check       All gates: lint, typecheck, imports, test — run before every push"
	@echo "  lint        ruff check + ruff format --check"
	@echo "  format      ruff format + ruff check --fix"
	@echo "  typecheck   pyright (strict)"
	@echo "  imports     import-linter contracts"
	@echo "  test        pytest"

check: lint typecheck imports test

lint:
	uv run ruff check .
	uv run ruff format --check .

format:
	uv run ruff format .
	uv run ruff check --fix .

typecheck:
	uv run pyright

imports:
	uv run lint-imports

test:
	uv run pytest
