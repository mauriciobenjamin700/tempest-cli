.DEFAULT_GOAL := help
PACKAGE := tempest_cli

.PHONY: help install check lint fix fmt fmt-check type test docs docs-serve build smoke clean

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-12s\033[0m %s\n", $$1, $$2}'

install: ## Sync every dependency group
	uv sync --all-extras --group docs

check: ## Run the gate on itself (lint + fmt-check + type + test)
	uv run tempest-cli check

lint: ## ruff check
	uv run tempest-cli lint

fix: ## Every ruff autofix, then format
	uv run tempest-cli fix

fmt: ## ruff format (writes)
	uv run tempest-cli format

fmt-check: ## ruff format --check
	uv run tempest-cli fmt-check

type: ## mypy
	uv run tempest-cli type

test: ## pytest
	uv run tempest-cli test

docs: ## Build the bilingual site (strict)
	uv run --group docs mkdocs build --strict

docs-serve: ## Serve the docs locally
	uv run --group docs mkdocs serve

build: ## Build sdist + wheel
	uv build

smoke: ## Install the built wheel in a clean venv and import it
	@rm -rf /tmp/$(PACKAGE)-smoke dist
	uv build
	uv venv --python 3.11 /tmp/$(PACKAGE)-smoke
	uv pip install --python /tmp/$(PACKAGE)-smoke/bin/python --quiet "$$(ls dist/*.whl)"
	/tmp/$(PACKAGE)-smoke/bin/python -c "import sys, tempest_cli as m, tempest_cli.main; \
		assert m.__version__, 'no __version__'; \
		heavy = {'fastapi', 'sqlalchemy', 'alembic', 'starlette', 'pydantic'}; \
		loaded = {name.split('.')[0] for name in sys.modules}; \
		assert not (heavy & loaded), f'pulled a web framework: {sorted(heavy & loaded)}'; \
		print('Smoke OK · version =', m.__version__)"
	/tmp/$(PACKAGE)-smoke/bin/tempest-cli --version
	@rm -rf /tmp/$(PACKAGE)-smoke

clean: ## Remove build and cache artifacts
	rm -rf dist build site .pytest_cache .mypy_cache .ruff_cache htmlcov .coverage
