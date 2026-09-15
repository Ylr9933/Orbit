UV ?= uv
PNPM ?= pnpm
WEB_PORT ?= 5173
PYTHON_VERSION := $(shell cat .python-version)

.PHONY: help setup check lint typecheck test build verify format dev-web check-tools
help:
	@echo "setup | check | test | build | verify | format | dev-web"
	@echo "verify = check + test + build; WEB_PORT controls dev-web"

check-tools:
	$(UV) run --no-project --python $(PYTHON_VERSION) scripts/dev/check_tools.py

setup: check-tools
	$(UV) sync --locked
	$(PNPM) install --frozen-lockfile

lint:
	$(UV) run --locked ruff check src/agent_infra tests scripts
	$(UV) run --locked ruff format --check src/agent_infra tests scripts
	$(UV) run --locked lint-imports --no-cache

typecheck:
	$(UV) run --locked mypy

check: lint typecheck
	$(PNPM) check
	$(UV) run --locked python scripts/ci/check_repository.py

test:
	$(UV) run --locked pytest -m "not integration and not e2e"

build:
	$(UV) build
	$(PNPM) build

verify: check test build

format:
	$(UV) run --locked ruff format src/agent_infra tests scripts
	$(UV) run --locked ruff check --fix src/agent_infra tests scripts
	$(PNPM) format

dev-web:
	$(PNPM) --filter @agent-infra/web dev --port $(WEB_PORT)
