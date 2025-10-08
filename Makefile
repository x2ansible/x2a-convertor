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

DOCKER ?= podman
IMAGE_NAME ?= x2a-convertor
IMAGE_TAG ?= latest

build:
	$(DOCKER) build -t $(IMAGE_NAME):$(IMAGE_TAG) .

run-container:
	$(DOCKER) run --rm -it $(IMAGE_NAME):$(IMAGE_TAG)

clean-container:
	$(DOCKER) rmi $(IMAGE_NAME):$(IMAGE_TAG)

.PHONY: check format ci-check install clean run-init build run-container clean-container
