.PHONY: install lint format test ingest dbt train api pipeline

install:
	uv sync
	uv run pre-commit install

lint:
	uv run ruff check .
	uv run ruff format --check .
	uv run mypy

format:
	uv run ruff check --fix .
	uv run ruff format .

test:
	uv run pytest

ingest:
	uv run python -m data_platform.ingestion.run

dbt:
	uv run dbt build --project-dir dbt --profiles-dir dbt

train:
	uv run python -m ml.training.train

api:
	uv run uvicorn services.api.main:create_app --factory --port 8010

pipeline: ingest dbt train
