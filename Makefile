check:
	uv run ruff check . --fix

format:
	uv run ruff format

ci-check:
	uv run ruff check . --output-format=github
	uv run ruff format --check

install:
	uv sync

.PHONY: check format ci-check install

