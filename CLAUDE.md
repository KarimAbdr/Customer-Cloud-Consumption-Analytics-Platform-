# Project: Customer 360 & Cloud Consumption Analytics Platform

Portfolio project for an SAP BDC / CPIT Customer 360 working-student application (data engineering + software engineering). Everything lives in one monorepo: pipelines, dbt models, ML training, API, dashboard, CI.

## Working mode (applies ONLY to this project)

The user works in manual mode and presses Enter consciously at every stage. They are learning while building, so:

1. Work in small stages. Before each stage, give a short explanation in Russian:
   - **Что это**: what is being built, in plain words.
   - **Зачем**: what problem it solves in the platform and in a real company.
   - **Почему так**: why this tool/pattern/architecture and not the alternatives.
   - **Что скажет интервьюер**: how to describe this decision on an interview.
2. Then stop and wait for the user's go-ahead before writing code for that stage. After the stage, show how to verify it (command + expected result).
3. Explain code decisions too (layering, naming, typing, tests), not only architecture. Keep it concise, no lecture walls.
4. Never skip ahead to the next stage without confirmation.
5. Explanations in Russian; code, comments, commit messages, docs and README in English.

## Decisions

- Orchestration: Apache Airflow (not Dagster). The pipeline must also run without Airflow via `make pipeline`; the DAG is a thin wrapper over the same entry points.
- Storage/SQL: DuckDB + Parquet, transformations in dbt-duckdb (bronze/silver/gold).
- ML: LightGBM churn model, tracked with MLflow, no AI/LLM features.
- Serving: FastAPI + Streamlit.
- Quality: uv, ruff, mypy, pytest, sqlfluff, pre-commit, GitHub Actions, Docker Compose.
- Cut order if time runs out: Streamlit, then Docker, then Airflow (keep `make pipeline`).
