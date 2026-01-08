DOCKER ?= podman
IMAGE_NAME ?= x2a-convertor
IMAGE_TAG ?= latest

check:
	uv run ruff check . --fix

format:
	uv run ruff format

type-check:
	uv run pyrefly check

ci-check:
	uv run ruff check . --output-format=github
	uv run ruff format --check
	uv run pyrefly check
	uv run pytest -m "not eval"

evals:
	uv run pytest -m "eval"

install:
	uv sync

clean:
	uv venv --clear
	rm -rf ./tmp

build:
	$(DOCKER) build -t $(IMAGE_NAME):$(IMAGE_TAG) .

run-container:
	$(DOCKER) run --rm -it $(IMAGE_NAME):$(IMAGE_TAG)

clean-container:
	$(DOCKER) rmi $(IMAGE_NAME):$(IMAGE_TAG)

# first step
run-init:
	uv run app.py init \
	  --source-dir ./examples/$(name) \
	  "I want to migrate this Chef repository to Ansible"

# second step
run-analyze:
	uv run app.py analyze \
	  --source-dir ./examples/$(name) \
	  "Analyze the Chef cookbook"

# third step
run-migrate:
	rm -rf ./examples/$(name)/ansible
	uv run app.py migrate \
	  --source-dir ./examples/$(name) \
	  --module $(module) \
	  --source-technology Chef --high-level-migration-plan migration-plan.md \
	  --module-migration-plan migration-plan-hello_world.md \
	  "Convert the hello_world cookbook"


generate-docs:
	uv run python scripts/generate_env_docs.py
	uv run python scripts/generate_cli_docs.py
	uv run python scripts/generate_usage_docs.py

.PHONY: check format ci-check evals install clean run-init run-analyze run-migrate build run-container clean-container generate-docs

