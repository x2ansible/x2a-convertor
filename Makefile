check:
	uv run ruff check . --fix

format:
	uv run ruff format

ci-check:
	uv run ruff check . --output-format=github
	uv run ruff format --check

install:
	uv sync

clean:
	uv venv --clear
	rm -rf ./tmp

run-init:
	uv run app.py init \
	  --source-dir ./input/$(name) \
	  "I want to migrate this Chef repository to Ansible"

.PHONY: check format ci-check install clean run-init
