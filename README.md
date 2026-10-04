# Customer 360 & Cloud Consumption Analytics Platform

[![CI](https://github.com/OWNER/REPO/actions/workflows/ci.yml/badge.svg)](https://github.com/OWNER/REPO/actions/workflows/ci.yml)

An end-to-end data and ML platform on synthetic B2B SaaS data: raw ingestion, a layered
warehouse built with dbt, a churn model tracked in MLflow, and an API that serves both
customer profiles and predictions. Everything lives in one monorepo and runs locally with
a single command.

> The data is synthetic (no real customer data). Distributions and the churn mechanism are
> documented in `data_platform/ingestion/synthetic.py`.

## Architecture

```text
synthetic generators
        |
        v
  bronze (Parquet, pandera contracts)        data_platform/ingestion
        |
        v
  silver (dbt, DuckDB: cleaned staging)      dbt/models/silver
        |
        v
  gold   (dbt: customer_features, customer_360)   dbt/models/gold
        |                         |
        v                         v
  LightGBM + MLflow          FastAPI service  <---  model loaded from MLflow
  ml/training                services/api
```

| Layer | Tooling | What it does |
|-------|---------|--------------|
| Bronze | pandas, pandera, Parquet | Generates raw tables and validates them against explicit data contracts |
| Silver | dbt-duckdb | Types, deduplicates and cleans; dbt tests guard keys and relations |
| Gold | dbt-duckdb | `customer_features` (ML input) and `customer_360` (business view) |
| ML | LightGBM, MLflow | Churn model, metrics and artifacts tracked per run |
| Serving | FastAPI, Pydantic | Customer lookup/filtering, portfolio summary and churn prediction |
| Dashboard | Streamlit | Thin client over the API: KPIs, segments, "call first" list, churn score |

## Quick start

Requirements: Python 3.12 and [uv](https://docs.astral.sh/uv/). On macOS, LightGBM also
needs OpenMP: `brew install libomp`.

```bash
make install     # uv sync + pre-commit hooks
make pipeline    # ingest -> dbt build -> train model
make api         # serve on http://localhost:8010 (OpenAPI docs at /docs)
make dashboard   # Streamlit UI on http://localhost:8501 (needs the API running)
```

```bash
curl localhost:8010/health
curl localhost:8010/customers/C000000
curl -X POST localhost:8010/predict/churn -H 'content-type: application/json' \
     -d '{"customer_id": "C000000"}'
```

Individual steps: `make ingest`, `make dbt`, `make train`.

## API

| Endpoint | Purpose |
|----------|---------|
| `GET /health` | Service status and whether a model is loaded |
| `GET /customers/{id}` | Customer 360 profile (404 if unknown) |
| `GET /customers?segment=&at_risk=&order=&limit=` | Filtered list; `order=value` sorts by contract value |
| `GET /portfolio/summary` | Portfolio KPIs and per-segment breakdown, aggregated in SQL over all customers |
| `POST /predict/churn` | Churn probability for a customer (503 if no model) |

## Model

LightGBM binary classifier, 5,000 customers, about 12% churn rate. One seeded run:

| Metric | Value |
|--------|-------|
| ROC-AUC | 0.787 |
| PR-AUC | 0.344 |

PR-AUC is reported next to ROC-AUC because the classes are imbalanced. A test asserts the
hold-out ROC-AUC stays between 0.70 and 0.95, so a leaked feature (suspiciously perfect
score) fails the build. Features are read from the same gold table in training and serving
to avoid training-serving skew.

## Quality gates

`make lint` and `make test` are the single source of truth. Pre-commit, CI and local runs
all call the same targets.

| Check | Tool |
|-------|------|
| Python lint and format | ruff |
| Types | mypy (strict) |
| SQL style | sqlfluff (duckdb dialect, dbt templater) |
| Tests | pytest: unit, dbt build in a temp warehouse, API integration |
| CI | GitHub Actions (`.github/workflows/ci.yml`) on every push and pull request |

## Key decisions

- **DuckDB + Parquet + dbt** instead of a cloud warehouse: zero infrastructure, the same
  bronze/silver/gold modelling and testing patterns.
- **Pandera data contracts at the bronze boundary**: bad data fails at ingestion, not in a
  dashboard.
- **LightGBM + MLflow**: strong tabular baseline with reproducible, tracked runs.
- **API as the single access point**: consumers never read DuckDB or load the model.
- **Pipeline without an orchestrator**: `make pipeline` runs the full flow; an Airflow DAG is
  planned as a thin wrapper over the same entry points.
- **Dashboard talks only to the API**: aggregates are computed server-side in SQL, so the page
  never pulls thousands of rows and never touches DuckDB or the model.

## Repository layout

```text
data_platform/   ingestion (synthetic data, Parquet writer) and pandera contracts
dbt/             dbt-duckdb project: sources, silver and gold models, data tests
ml/              training and model loading (MLflow)
services/api/    FastAPI service
services/dashboard/  Streamlit dashboard (API client, metrics, page)
tests/           pytest suite
docs/STAGES.md   build log: what, why, evidence for every stage
```

## Roadmap

Planned, not built yet: Docker Compose, Airflow DAG.
Known gaps (no hyper-parameter search, no auth on the API) are listed per stage in
`docs/STAGES.md`.
