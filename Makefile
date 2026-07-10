.PHONY: check lint format typecheck imports test

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
