# Local development. Everything here runs offline except `data`.
.DEFAULT_GOAL := help
PY ?= python
CONFIG ?= configs/cn_csi300.yaml

help:  ## show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN{FS=":.*?## "}{printf "  \033[36m%-16s\033[0m %s\n", $$1, $$2}'

setup:  ## create a venv and install the package with dev extras
	$(PY) -m venv .venv && . .venv/bin/activate && pip install -U pip && pip install -e ".[qlib,llm,dev]"
	@echo "now: source .venv/bin/activate && make db && make test"

db:  ## create/upgrade the database (SQLite by default, DATABASE_URL for Postgres)
	$(PY) -m alembic upgrade head
	alphalab db status -c $(CONFIG)

migration:  ## autogenerate a migration after changing models: make migration M="what changed"
	$(PY) -m alembic revision --autogenerate -m "$(M)"

test:  ## run the test suite (no data, no network, no model needed)
	$(PY) -m pytest -q

lint:  ## ruff
	$(PY) -m ruff check src tests

data:  ## download the free CN dataset (~570MB, the only step needing network)
	alphalab download-cn -c $(CONFIG)

llm-check:  ## verify the configured model endpoints (Ollama / vLLM / Anthropic / mock)
	alphalab llm-check -c $(CONFIG)

offline:  ## full suite with no network and no model: mock LLM, local data
	alphalab llm-check -c configs/local_offline.yaml
	alphalab sanity -c configs/local_offline.yaml
	alphalab discover -c configs/local_offline.yaml
	alphalab model -c configs/local_offline.yaml
	alphalab audit -c configs/local_offline.yaml
	alphalab journal -c configs/local_offline.yaml

cycle:  ## one closed research cycle with the configured LLM
	alphalab cycle -c $(CONFIG) -n 15

lock:  ## pin the full dependency tree into constraints.txt (reproducible builds)
	$(PY) -m pip install -q pip-tools && \
	$(PY) -m piptools compile --all-extras --strip-extras -o constraints.txt pyproject.toml

image:  ## build the lab image
	docker build -t alphalab:$(shell $(PY) -c "import tomllib,pathlib;print(tomllib.loads(pathlib.Path('pyproject.toml').read_text())['project']['version'])") .

up:  ## start postgres. Add: make up PROFILE=local-llm (ollama) | gpu (vllm) | app (dashboard)
	docker compose $(if $(PROFILE),--profile $(PROFILE),) up -d

down:  ## stop local services
	docker compose --profile "*" down

clean:  ## remove caches and generated run artefacts (keeps results/)
	rm -rf runs/.cache .pytest_cache .ruff_cache **/__pycache__

.PHONY: help setup db migration test lint data llm-check offline cycle lock image up down clean
