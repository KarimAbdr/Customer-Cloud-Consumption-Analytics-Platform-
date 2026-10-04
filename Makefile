.PHONY: install lint format test ingest dbt train api dashboard pipeline

install:
	uv sync
	uv run pre-commit install

lint:
	uv run ruff check .
	uv run ruff format --check .
	uv run mypy
	uv run sqlfluff lint dbt/models

format:
	uv run ruff check --fix .
	uv run ruff format .
	uv run sqlfluff fix dbt/models

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

dashboard:
	uv run streamlit run services/dashboard/app.py

pipeline: ingest dbt train
