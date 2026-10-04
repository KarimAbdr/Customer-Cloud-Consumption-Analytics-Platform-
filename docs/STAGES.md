# Stage Log

Running log of every build stage, written after the owner approves the stage.
Purpose: hand this file to an AI reviewer or a teammate to understand the whole
project quickly. Each entry: what was done, why, files, commands, verification.

---

## Stage 0 - Project skeleton and tooling

- **Status:** approved
- **What:** Monorepo layout (`data_platform/`, `ml/`, `services/`, `tests/`, `data/`), tooling config and a smoke test.
- **Why:** One reproducible setup (uv, ruff, mypy strict, pytest, pre-commit) before any business code, so every later stage is linted, typed and tested from day one.
- **Files:** `pyproject.toml`, `Makefile`, `.pre-commit-config.yaml`, `.gitignore`, `.python-version`, `CLAUDE.md`, `tests/test_smoke.py`, package `__init__.py` files.
- **Commands:** `make install`, `make lint`, `make test`.
- **Commit:** `dfe0744 chore: bootstrap project skeleton with tooling`

---

## Stage 1 - Synthetic bronze data: customers, contracts, daily usage

- **Status:** approved
- **What:** Reproducible generators (`seed`-based) for `customers`, `contracts` and `daily_usage`, with realistic statistics instead of uniform random values.
- **Why:** There is no real SAP data. All downstream layers (dbt, ML, API) need data with believable shape, so the churn model later has a real but noisy signal to learn.
- **Statistical design** (all parameters in `SyntheticConfig`, plausible B2B SaaS assumptions, not real SAP figures):
  - Segments SMB / MID_MARKET / ENTERPRISE with weights 60/30/10.
  - Employees: log-normal per segment (right-skewed, a few very large customers).
  - Usage: customer level x exponential trend x weekend factor (0.55) x log-normal noise x rare spikes (2-4x).
  - Contracts: terms 12/24/36 months, fee per employee with a volume discount.
  - About 4% NULL in `industry` to mimic dirty data.
- **Files:**
  - `data_platform/ingestion/synthetic.py` (new): `generate_customers`, `generate_contracts`, `generate_usage`, `SyntheticConfig`.
  - `tests/test_synthetic_stage1.py` (new): 15 tests.
  - `docs/STAGES.md` (new): this log.
- **TDD evidence:**
  - RED: `uv run pytest tests/test_synthetic_stage1.py` -> `ModuleNotFoundError: No module named 'data_platform.ingestion.synthetic'` (collection error, implementation missing).
  - GREEN: `uv run pytest` -> `15 passed`.
  - Coverage: `uv run pytest --cov=data_platform` -> `synthetic.py` 100%.
  - Quality gates: `make lint` (ruff, ruff-format, mypy strict) clean.
- **What the tests guarantee:** determinism per seed, unique IDs, empty input handled, right-skewed sizes, realistic segment mix, Enterprise > Mid > SMB size, NULL share bounds, one contract per customer with `end > start`, usage referential integrity, one row per customer per day, lower weekend usage, >95% unique usage values.
- **Verify:** `make test` -> 15 passed.
- **Known gap:** no churn labels or support tickets yet (Stage 2). Dates in contracts use 30-day months.

---

## Stage 2 - Support tickets and churn labels

- **Status:** approved
- **What:** `generate_dissatisfaction`, `generate_tickets`, `generate_churn_labels`; `generate_usage` got an optional `dissatisfaction` argument.
- **Why:** Churn is the ML target. A hidden (latent) dissatisfaction variable drives usage decline, ticket volume and churn probability, so features correlate with the label like in real data, but noisily. No deterministic formula to reverse-engineer, and no target leakage.
- **Design** (parameters in `SyntheticConfig`):
  - Latent dissatisfaction ~ N(0,1), kept outside every table.
  - Tickets: Poisson per customer per month; rate by segment (0.3 / 1.0 / 3.0) times `exp(0.5 * dissatisfaction)`.
  - Usage trend: daily log-trend reduced by `0.0015 * dissatisfaction`.
  - Churn: Bernoulli of a logistic model (latent, 12-month contract, SMB, plus noise). Calibrated to roughly 11-13% churn (checked on seeds 1, 7, 42, 99).
- **Files:**
  - `data_platform/ingestion/synthetic.py` (changed): new generators, new config fields, optional argument in `generate_usage` (backward compatible).
  - `tests/test_synthetic_stage2.py` (new): 11 tests.
- **TDD evidence:**
  - RED: `uv run pytest tests/test_synthetic_stage2.py` -> `ImportError: cannot import name 'generate_churn_labels'`.
  - First GREEN attempt: 25 passed, 1 failed (churn share 16.55% > 15%). Fixed by calibrating `churn_intercept` from -2.6 to -3.1 (test not changed).
  - GREEN: `uv run pytest` -> `26 passed`; coverage of `synthetic.py` 100%; `make lint` clean.
- **What the tests guarantee:** determinism, one ticket row per customer per month, non-negative integer counts, Enterprise opens more tickets than SMB, churn share 8-15%, binary one-per-customer labels, churners have more tickets and a worse usage trend, no latent column in any table, empty input handled.
- **Verify:** `make test` -> 26 passed.
- **Known gap:** churn is a single binary label per customer (no churn date); tickets are monthly counts only (no text or severity).

---

## Stage 3 - Bronze layer: pandera contracts, Parquet writer, `make pipeline`

- **Status:** approved
- **What:** Ingestion entry point that generates all five bronze tables, validates them against pandera schemas and writes `data/bronze/*.parquet`.
- **Why:** Downstream layers (DuckDB/dbt, ML, API) read files, not Python functions. Bronze is the raw layer; the schema check is the data contract at its boundary. One entry point means the future Airflow DAG is a thin wrapper and `make pipeline` works without Airflow.
- **Design:**
  - `build_tables` (pure generation) -> `write_bronze` (validate all, then write) -> `run_ingestion` (orchestrates) -> `main` (argparse CLI).
  - Validate every table before writing anything, so invalid data leaves no files behind.
  - Atomic write: `<name>.parquet.tmp` then rename, so a crash never leaves a half-written file.
  - Defaults: 5000 customers, 180 days, seed 42 (about 900k usage rows, runs in under a second).
  - `data/` is git-ignored; only code is versioned.
- **Files:**
  - `data_platform/quality/schemas.py` (new): `BRONZE_SCHEMAS` for 5 tables (types, uniqueness, value ranges, allowed categories, strict columns).
  - `data_platform/ingestion/run.py` (new): library and CLI.
  - `tests/test_bronze_ingestion.py` (new): 7 tests.
  - `Makefile` (changed): `pipeline` target runs `python -m data_platform.ingestion.run`.
- **TDD evidence:**
  - RED: `ModuleNotFoundError: No module named 'data_platform.ingestion.run'`.
  - GREEN: `uv run pytest` -> `33 passed`. Coverage 99% (uncovered: the `__main__` guard line).
  - `make lint` clean; `make pipeline` writes 5 files (daily_usage 900,000 rows, 4.9 MB).
- **What the tests guarantee:** one Parquet file per table, correct row counts, data reads back equal to what was generated, same seed gives identical output, re-run overwrites cleanly with no leftover `.tmp`, schema violation (negative usage) raises `SchemaError` and writes nothing, CLI exits 0 and prints a summary.
- **Verify:** `make pipeline` then `ls data/bronze`; `make test` -> 33 passed.
- **Known gap:** `check_dtype=False` in the round-trip test because Parquet may change string/datetime resolution; values are compared exactly. Support tickets cover `days // 30` months.

---

## Stage 4 - Silver layer: DuckDB + dbt models and tests

- **Status:** approved
- **What:** dbt-duckdb project that reads bronze Parquet as sources and builds five cleaned silver tables, with dbt data tests.
- **Why:** Bronze is raw. Silver is the single place where data is renamed, typed and cleaned, so every later layer (gold, ML, API) starts from trusted tables. dbt gives a dependency graph, versioned SQL and tests that run on every build. Pandera guards the bronze boundary; dbt tests guard relations and business rules between layers.
- **Design:**
  - Sources read Parquet directly via `meta.external_location` (`BRONZE_DIR` env var, default `data/bronze`); warehouse path from `DUCKDB_PATH` (default `data/warehouse.duckdb`). Run dbt from the repo root.
  - `stg_customers`: missing `industry` -> `'UNKNOWN'`.
  - `stg_contracts`: columns renamed to `contract_start_date` / `contract_end_date`, cast to DATE.
  - `stg_daily_usage`: `usage_date` cast to DATE. `stg_support_tickets`: `month` -> `ticket_month` (DATE). `stg_churn_labels`: `churned` int -> `is_churned` boolean.
  - 19 dbt data tests (24 dbt nodes with the 5 models): unique, not_null, accepted_values (segment, term_months) and relationships to `stg_customers`.
- **Files:**
  - `dbt/dbt_project.yml`, `dbt/profiles.yml`, `dbt/models/sources.yml`, `dbt/models/silver/schema.yml` (new).
  - `dbt/models/silver/stg_*.sql` (5 new models).
  - `tests/test_dbt_silver.py` (new): runs `dbt build` on a small generated dataset in a temp dir and checks the result with DuckDB.
  - `Makefile` (changed): new `ingest` and `dbt` targets; `pipeline` = `ingest` then `dbt`.
  - `pyproject.toml`, `uv.lock` (changed): added `dbt-duckdb`, `duckdb`.
- **TDD evidence:**
  - RED: with sources and schema tests but no models, `dbt build` ran nothing, no warehouse was created, and 8 checks failed with `database does not exist`.
  - GREEN: `uv run pytest tests/test_dbt_silver.py` -> 8 passed; full suite `41 passed`.
  - `make pipeline` -> `Done. PASS=24 WARN=0 ERROR=0 (TOTAL=24)`; `make lint` clean.
- **What the tests guarantee:** each silver table has exactly the expected columns in order, row counts equal bronze, no NULL `industry`, `usage_date` is DATE, and all dbt data tests (keys, categories, referential integrity) pass.
- **Verify:** `make pipeline`; `make test` -> 41 passed.
- **Known gap:** sqlfluff is not wired in yet (planned in the quality stage). The pytest runs the real `dbt` binary, so `make test` takes about 4 seconds longer.

---

## Stage 5 - Gold layer: ML features and Customer 360 view

- **Status:** approved
- **What:** Two dbt gold models: `customer_features` (one row per customer, ML features + churn target) and `customer_360` (business view for dashboard/API).
- **Why:** Gold is the layer consumed by ML, API and dashboard. Features are computed once in SQL and reused by training and serving, which avoids training-serving skew. The project name is Customer 360: one table with the whole picture of a customer.
- **Design:**
  - Features: segment, employees, industry, contract term and fee; usage mean of first 30 and last 30 days and their ratio (`usage_trend_ratio`); weekend usage share; `usage_peak_ratio` (max / mean); total and monthly-average tickets.
  - Windows are relative to each customer's own first and last usage date. Features use only the observation window; the churn label comes from a hidden variable that is not in any table, so there is no leakage.
  - `customer_360` adds `contract_end_date`, `annual_contract_value` (fee x 12), `avg_daily_usage` and `is_at_risk` (`usage_trend_ratio < 0.85`).
  - Models land in the `main` schema of DuckDB (no custom schema configured).
- **Files:**
  - `dbt/models/gold/customer_features.sql`, `dbt/models/gold/customer_360.sql`, `dbt/models/gold/schema.yml` (new); `dbt/dbt_project.yml` (gold config).
  - `tests/test_dbt_gold.py` (new): 7 tests. `tests/dbt_helpers.py` (new): shared `build_warehouse` / `query`. `tests/test_dbt_silver.py` (refactored to use the helper). `tests/__init__.py` (new, fixes mypy duplicate-module error).
- **TDD evidence:**
  - RED: 7 gold tests failed with `Table with name customer_360 does not exist`; the 8 silver tests still passed after the helper refactor.
  - GREEN: `uv run pytest` -> `48 passed`; `make pipeline` -> `dbt Done. PASS=35 ERROR=0`; `make lint` clean.
  - Signal check on full data (5000 customers): churned vs retained mean trend ratio 0.889 vs 1.158, mean tickets 7.8 vs 4.8; churn rate 11.7%; 961 customers flagged at risk.
- **What the tests guarantee:** exact column contracts for both tables, one row per customer, no NULL numeric features, feature values equal an independent pandas computation for 5 customers, churn rate equals silver, `is_at_risk` is exactly `trend < 0.85`, plus dbt tests (unique, not_null, relationships, accepted_values).
- **Verify:** `make pipeline`; `make test` -> 48 passed.
- **Known gap:** 0.85 risk threshold is a heuristic, not model output; the ML stage will provide real churn probabilities. Features are computed once over the whole window (no train/test time split yet).

---

## Stage 6 - Churn model: LightGBM + MLflow

- **Status:** approved
- **What:** `ml/training/train.py` reads `customer_features` from DuckDB, trains a LightGBM classifier, evaluates it on a stratified hold-out and logs params, metrics and the model to MLflow. `make train` runs it; `make pipeline` is now ingest -> dbt -> train.
- **Why:** This is the ML core of the platform. Experiment tracking makes every model version reproducible (data size, params, metrics, artifact).
- **Design:**
  - `train_model(features, seed)` is a pure function (no DB, no MLflow), so it is unit-testable. DB loading (`load_features`) and logging (`train_and_log`) are separate.
  - Metrics: ROC-AUC and PR-AUC. Churn is about 12%, so accuracy would mislead and PR-AUC shows quality on the minority class.
  - Stratified 75/25 split with fixed seed; class imbalance handled with `scale_pos_weight`; `deterministic=True`, `n_jobs=1` for reproducible results.
  - `customer_id` and the target are excluded from features.
  - `ChurnModel` bundles the estimator with the category levels from training, so serving encodes `segment` / `industry` identically; unseen levels become missing values instead of raising.
  - MLflow 3 notes: the plain file store is disabled by default, so tracking uses SQLite (`mlruns/mlflow.db`) with artifacts in `mlruns/artifacts`. The model is saved with `serialization_format="cloudpickle"` because the default skops format rejects the wrapper type; only load models from a store you control.
- **Files:**
  - `ml/training/train.py` (new). `tests/test_churn_training.py` (new, 7 tests).
  - `Makefile` (`train` target, `pipeline` extended), `pyproject.toml` (deps `lightgbm`, `scikit-learn`, `mlflow`; mypy overrides for untyped ML libs), `uv.lock`.
- **Environment note:** LightGBM on macOS needs OpenMP: `brew install libomp`. On macOS 14 Homebrew builds it from source (about 6 minutes).
- **TDD evidence:**
  - RED: `ModuleNotFoundError: No module named 'ml.training.train'`.
  - First GREEN attempts: 5 of 7 passed. Two failures came from MLflow 3 (file store disabled; skops untrusted types). Fixed in implementation and in the tracking API (`tracking_dir` instead of a raw URI); test assertions were not weakened.
  - GREEN: `uv run pytest` -> `55 passed`; `make lint` clean; the pandas category warning was fixed rather than silenced.
  - Full run (`make pipeline`, 5000 customers): ROC-AUC 0.787, PR-AUC 0.344 (churn base rate about 11.7%). Superseded in Stage 14: class reweighting was removed (ROC-AUC 0.796, PR-AUC 0.339, Brier 0.090).
- **What the tests guarantee:** no id/target in features, same seed gives identical predictions, hold-out ROC-AUC between 0.70 and 0.95 (above chance, and not suspiciously perfect, which would indicate leakage), probabilities in [0, 1], unseen categories do not break prediction, MLflow run contains `roc_auc`, `pr_auc` and the seed, and a model reloaded from MLflow predicts identically.
- **Verify:** `make train` prints `run_id`, `roc_auc`, `pr_auc`; `make test` -> 55 passed.
- **Known gap:** no hyper-parameter search and no time-based split (data is a single synthetic window); metrics come from one seed; no model registry or promotion step yet.

---

## Stage 7 - Serving: FastAPI service

- **Status:** approved
- **What:** `services/api` with `GET /health`, `GET /customers/{id}`, `GET /customers?segment=&at_risk=&limit=` and `POST /predict/churn`. Run with `make api` (port 8010).
- **Why:** Dashboard and other consumers should not read DuckDB or load the model themselves. The API is the single access point and shows the model running as a service, not only trained in a notebook.
- **Design:**
  - Layers: routes (thin) -> `CustomerRepository` (read-only DuckDB, parameterized SQL) and `ChurnPredictor` (model wrapper); Pydantic schemas define the response contract; OpenAPI at `/docs` is generated from the types.
  - Dependencies are injected: `create_app(repository, predictor)` for tests, environment-based defaults (`DUCKDB_PATH`, `MLFLOW_TRACKING_DIR`, `MLFLOW_EXPERIMENT`) in production. Start with `uvicorn services.api.main:create_app --factory`.
  - The model is loaded once at startup from the latest MLflow run (`ml/inference/registry.py`); missing model -> `/health` reports `model_loaded: false` and `/predict/churn` answers 503.
  - Prediction reads features from `customer_features`, the same table used for training (no training-serving skew).
  - Errors: unknown customer 404, invalid `segment` / `limit` 422 (validated by Pydantic types).
- **Bug found by live run, fixed with a regression test:** a model trained by `python -m ml.training.train` was pickled with the class `__main__.ChurnModel`, so the API process crashed at startup (`AssertionError` in `load_model`). Unit tests missed it because they trained via import. Fix: `ChurnModel` moved to `ml/training/model.py` (never run as `__main__`). New test `test_model_trained_via_cli_loads_in_a_different_process` failed first (RED), passes now.
- **Environment note:** port 8000 was already used by a Docker container on the dev machine, so the API uses 8010.
- **Files:**
  - `services/api/{main,schemas,repository,predictor}.py`, `ml/inference/registry.py`, `ml/training/model.py` (new); `ml/training/train.py` (class moved out).
  - `tests/test_api.py` (new, 16 tests), `tests/test_churn_training.py` (+1 regression test).
  - `Makefile` (`api` target), `pyproject.toml` / `uv.lock` (`fastapi`, `uvicorn`, `httpx`).
- **TDD evidence:**
  - RED: `ModuleNotFoundError: No module named 'ml.inference.registry'`.
  - GREEN: 16 API tests passed on first implementation; the CLI regression test was added after a live smoke test exposed the pickle bug (RED `AssertionError`, then GREEN).
  - Final: `uv run pytest` -> `72 passed`; `make lint` clean.
  - Live smoke test on the real warehouse: `/health` -> `{"status":"ok","model_loaded":true}`; `/customers/C000000` returned the profile; `/predict/churn` returned `churn_probability` 0.427; unknown id -> 404.
- **What the tests guarantee:** health with and without a model, customer payload has exactly the contract fields, 404 for unknown customer (message contains the id), segment and at-risk filters, limit respected, 422 for bad segment / limit 0 / limit 1001, prediction equals `predict_proba` of the model for the same customer, 404 unknown customer on predict, 503 without a model, 422 for a missing body field, the latest-model loader returns a usable model and fails clearly on an empty store.
- **Verify:** `make pipeline`, then `make api` and `curl localhost:8010/health`; `make test` -> 72 passed.
- **Known gap:** no authentication, rate limiting or request logging; no batch prediction endpoint; model is only reloaded on restart.

---

## Stage 8 - CI, SQL linting and README

- **Status:** approved
- **What:** sqlfluff for dbt models, a GitHub Actions workflow, a project README.
- **Why:** Python was linted (ruff, mypy) but SQL was not. CI makes "tests exist" verifiable on every push, and the README is the first thing a reader opens.
- **Design:**
  - `.sqlfluff`: duckdb dialect, dbt templater (`sqlfluff-templater-dbt`), lowercase keywords/functions to match the existing models, 100-char lines.
  - `ST06` (column order) is disabled on purpose: column order in `customer_features` is the model's feature order and `customer_360` is a consumer-facing contract; reordering to satisfy a style rule would change behaviour. `RF04` (keyword-like identifiers) is also excluded.
  - `make lint` now runs sqlfluff; `make format` runs `sqlfluff fix`; a local pre-commit hook lints `dbt/**/*.sql`.
  - `.github/workflows/ci.yml`: checkout, `astral-sh/setup-uv`, `uv sync --locked`, `make lint`, `make test`. Same commands as local. No data is needed from the repo: tests build their own bronze and dbt warehouse in temp directories. `concurrency` cancels superseded runs.
- **Files:** `.sqlfluff`, `.sqlfluffignore`, `.github/workflows/ci.yml`, `README.md`, `Makefile`, `.pre-commit-config.yaml`, `pyproject.toml`, `uv.lock`.
- **Verification evidence:**
  - RED: `uv run sqlfluff lint dbt/models` -> 2 violations (`ST06` in `customer_360.sql` and `customer_features.sql`).
  - GREEN: after the rule decision above, `All Finished!` with no violations.
  - `make lint` clean; `make test` -> `72 passed`; workflow YAML parses and uses only the commands above.
- **Not verified locally:** the GitHub Actions run itself (needs a push to GitHub). The first run on Linux may reveal environment differences.
- **README badge:** points at `KarimAbdr/Customer-Cloud-Consumption-Analytics-Platform-`; the first GitHub Actions run on Linux was green (reported by the owner).

---

## Stage 9 - Streamlit dashboard

- **Status:** approved
- **What:** `services/dashboard` with an API client, pure portfolio metrics and a thin Streamlit page. Run with `make dashboard` (port 8501; needs `make api` on 8010, override with `API_URL`).
- **Why:** Gives the platform a business-facing surface: portfolio KPIs, segment breakdown, "call first" list of at-risk customers by contract value, and a customer detail with churn probability.
- **Design:**
  - The dashboard only talks to the API (`ApiClient`, httpx); it never opens DuckDB or loads the model.
  - `metrics.py` holds all calculations as pure pandas functions; `app.py` only renders. Streamlit code is hard to unit-test, so everything breakable lives outside it.
  - `ApiClient` returns the API's own Pydantic models, so a contract change breaks a test instead of the page. Unreachable API / 5xx raise `ApiUnavailableError` (page shows a hint to run `make api`); unknown customer or missing model return `None`.
- **Files:** `services/dashboard/{client,metrics,app}.py`, `tests/test_dashboard_client.py` (10 tests), `tests/test_dashboard_metrics.py` (8 tests), `Makefile`, `pyproject.toml`, `uv.lock` (`streamlit`).
- **TDD evidence:**
  - RED: both new test files failed at collection (modules did not exist).
  - GREEN: `uv run pytest tests/test_dashboard_*.py` -> `18 passed`; `make lint` clean.
  - Live check on the real warehouse: the page script was executed with `streamlit.testing.AppTest` against a running API: no exceptions, metrics Customers 1,000 / At risk 198 / share 19.8% / revenue at risk 8,889,850 / churn probability 42.7% for `C000000`.
- **What the tests guarantee:** KPI counts, share and revenue at risk, empty portfolio gives zeros, one summary row per segment in business order (SMB, MID_MARKET, ENTERPRISE), priority list contains only at-risk customers sorted by contract value and respects `top`; client parses real API responses, filters by segment, 404 -> `None`, no model -> `None`, unreachable API and 500 raise a clear error, `API_URL` is honoured.
- **Known gap (closed in Stage 10):** the API capped `limit` at 1000, so the dashboard showed the first 1,000 of 5,000 customers. The Streamlit page itself has no automated test in CI beyond the metrics and client tests; the visual layout was not checked in a browser.

---

## Stage 10 - Portfolio summary endpoint

- **Status:** approved
- **What:** `GET /portfolio/summary` (customers, at-risk count and share, annual revenue at risk, per-segment breakdown) and `order=value` on `GET /customers`. The dashboard now uses both.
- **Why:** The dashboard showed KPIs over the first 1,000 customers only (API page limit) while the warehouse holds 5,000. Aggregation belongs on the server, in SQL, over the whole table.
- **Design:**
  - `CustomerRepository.portfolio_summary` runs one `group by segment` query in DuckDB; totals and share are derived from the segment rows, so segments always add up to the totals. Empty portfolio gives zeros, not a division error.
  - `order` is a closed `Literal["id", "value"]` mapped to fixed SQL fragments (no user text reaches the SQL); invalid value gives 422. `value` sorts by contract value descending with `customer_id` as tie-break, so the "call first" list is a true top-N over all customers.
  - Dashboard: KPIs and chart come from the summary; the segment selector recomputes KPIs from the segment rows. `metrics.py` was rewritten around the summary (the old pandas aggregation over a row sample was removed).
  - Scope change versus the proposal: no `?segment=` parameter on the endpoint, because the per-segment breakdown already contains it and the dashboard filters client-side.
- **Files:** `services/api/{schemas,repository,main}.py`, `services/dashboard/{client,metrics,app}.py`, `tests/test_api.py` (+5), `tests/test_dashboard_client.py` (+2), `tests/test_dashboard_metrics.py` (rewritten, 5), `README.md` (API table, dashboard, roadmap).
- **TDD evidence:**
  - RED: 7 tests failed for the intended reasons (404 on the new route, 422 expected for `order`, missing client methods); the metrics test file failed at collection.
  - A first version of the ordering test passed without any implementation: the test warehouse has a single at-risk customer, so the list was trivially sorted. The test was rewritten to use all customers and now asserts that id order and value order differ (so it can tell them apart); it failed RED afterwards.
  - GREEN: `uv run pytest` -> `94 passed`; `make lint` clean.
  - Live check, real warehouse: `/portfolio/summary` -> 5000 customers, 961 at risk (19.2%), revenue at risk 40,239,553; the dashboard script run via `streamlit.testing.AppTest` shows Customers 5,000, no exceptions, no sampling caption.
- **What the tests guarantee:** the summary equals an independent SQL count per segment and in total, segments add up to the total, share = at_risk / customers, empty warehouse gives zeros, `order=value` returns the true top 10 across the portfolio, invalid `order` gives 422, the client parses the summary and honours `order`, KPIs for a segment selection count only that selection.
- **Known gap:** the page layout was not checked in a browser; the detail section still issues API calls on every rerun (no caching); revenue-at-risk uses annual contract value of at-risk customers (a business definition, not a forecast).

---

## Stage 11 - Docker Compose

- **Status:** approved
- **What:** `Dockerfile`, `.dockerignore`, `docker-compose.yml`; `make up` / `make down`.
- **Why:** One command runs the whole platform without installing Python, uv or libomp; the container is the deployable unit.
- **Design:**
  - One image, three roles by command: `pipeline` (`make pipeline`, one-shot, `restart: "no"`), `api` (uvicorn on 8010) and `dashboard` (Streamlit on 8501, `API_URL=http://api:8010`).
  - Startup order: `api` waits for `pipeline` with `service_completed_successfully`; `dashboard` waits for `api` with `service_healthy` (health check calls the existing `/health`).
  - Warehouse (`/app/data`) and model store (`/app/mlruns`) are named volumes, not part of the image. The pipeline is the single writer; the API only reads.
  - The pipeline runs `make pipeline`, so the container uses the same definition as the local flow (`uv run --no-sync`, dependencies baked in by `uv sync --locked --no-dev`). Dependency layer is cached until `pyproject.toml` / `uv.lock` change.
  - Non-root user (uid 1000); `.dockerignore` keeps `.venv`, `data`, `mlruns`, `.git`, tests and docs out of the image. `libgomp1` is installed for LightGBM.
- **Files:** `Dockerfile`, `.dockerignore`, `docker-compose.yml`, `tests/test_compose.py` (10 tests), `Makefile`, `README.md`, `pyproject.toml` / `uv.lock` (dev: `pyyaml`, `types-pyyaml`).
- **TDD evidence:**
  - RED: `docker compose config` -> `no configuration file provided: not found`; `tests/test_compose.py` -> `FileNotFoundError` for `docker-compose.yml`.
  - GREEN: `tests/test_compose.py` -> `10 passed`; `docker compose config -q` valid; `docker compose build` succeeded (3m50s cold).
  - Image size: first version 4.38 GB. `docker history` showed two avoidable layers: uv's package cache left inside the `uv sync` layer (about 1.1 GB) and `chown -R /app` copying the whole venv into a new layer (1.03 GB). Fixed with `uv sync --no-cache` and chowning only `data`, `mlruns`, `dbt`. Result: 1.61 GB; the full live run was repeated on the smaller image (pipeline 35/35 dbt, ROC-AUC 0.787, API, dashboard, uid 1000) with the same numbers.
  - Live run (`docker compose up -d`): `pipeline` exited 0 (ROC-AUC 0.787, PR-AUC 0.344, identical to the local run), API healthy, `/portfolio/summary` -> 5000 customers / 961 at risk, `/predict/churn` for `C000000` -> 0.427, `localhost:8501/_stcore/health` -> `ok`, dashboard script run inside the container via `AppTest` showed Customers 5,000 with no exceptions. Containers ran as uid 1000. Stack removed afterwards with `docker compose down -v`.
- **What the tests guarantee:** the three services exist, startup ordering conditions, dashboard reaches the API by service name, pipeline never restarts, API and pipeline share both volumes, documented ports are published, all services use one image, Dockerfile switches to a non-root user, `.dockerignore` excludes local state. They check the file, not a running stack; the live run above is the end-to-end proof.
- **Known gaps:** the image is 1.61 GB, mostly the Python dependencies themselves (venv about 980 MB: pyarrow, scipy, duckdb, mlflow, pandas, sklearn, streamlit); going lower means splitting dependencies per role (e.g. the dashboard does not need lightgbm/mlflow) or dropping libraries; the image build is not part of CI; the pipeline reruns on every `make up` (deterministic, but it rewrites the warehouse while nothing else runs); no `restart` policy or resource limits for api/dashboard; the page layout was not checked in a browser.

---

## Stage 12 - Airflow DAG

- **Status:** approved
- **What:** `dags/customer360_pipeline.py`: daily DAG `ingest -> dbt_build -> train_model`; `apache-airflow` 3.2.2 added as a dev dependency.
- **Why:** An orchestrator adds schedule, retries, run history and a dependency graph, which a Makefile does not provide. The DAG is a wrapper, not a second definition of the pipeline.
- **Design:**
  - Each task is a `BashOperator` running one existing target (`make ingest`, `make dbt`, `make train`) from the repository root; tasks are separate so a retry reruns only the failed step.
  - `schedule="@daily"`, `catchup=False`, `retries=2`, `retry_delay=5 min`.
  - Airflow lives in the `dev` dependency group: `make test` / CI can import the DAG, the Docker image (`uv sync --no-dev`) does not carry it.
  - `tests/conftest.py` points `AIRFLOW_HOME` to a temp directory, so tests never touch an existing `~/airflow` (the dev machine has one from earlier work; it was not modified).
  - Not included on purpose: Airflow scheduler / web UI / metadata database in Docker Compose.
- **Files:** `dags/customer360_pipeline.py`, `tests/test_airflow_dag.py` (11 tests), `tests/conftest.py`, `pyproject.toml`, `uv.lock`, `README.md`.
- **TDD evidence:**
  - RED: with Airflow installed, the DAG tests failed with `KeyError: 'customer360_pipeline'` (the DAG did not exist).
  - GREEN: `tests/test_airflow_dag.py` -> `11 passed`; `make test` -> `115 passed`; `make lint` clean (mypy strict).
  - Two test fixes on the way: mypy strict objections to Airflow's optional types, and the schedule assertion (the DAG stores an `airflow.sdk` timetable whose `expression` is `"@daily"`, not the core class).
- **What the tests guarantee:** DAG files import without errors, the DAG is registered with exactly the three tasks, order is ingest -> dbt -> train, each task's command is exactly its `make` target (no logic in the DAG), every target exists in the Makefile, tasks run from the repository root, retries with a delay are configured, schedule is daily without catch-up.
- **Not verified / known gaps:**
  - End-to-end execution under Airflow: `airflow dags test customer360_pipeline` (isolated `AIRFLOW_HOME`, fresh SQLite) failed inside Airflow's own execution API (`AttributeError: 'State' object has no attribute 'svcs_registry'`) before any `make` command ran. The cause was not investigated; a plausible, unconfirmed one is that this project's pinned library versions are newer than the ones Airflow 3.2.2 is tested with. The commands themselves are the same `make` targets that `make pipeline` and the Docker `pipeline` service already ran successfully.
  - The Docker image was not rebuilt after adding the dev dependency; Airflow is outside the `--no-dev` install, but this was not re-run.
  - Airflow's dependency tree adds about 68 packages to `uv.lock` and some seconds to CI.

---

## Stage 13 - Public demo bundle for Hugging Face Spaces (superseded by Stage 13b)

- **Status:** approved
- **What:** `make space-bundle` generates `dist/space`, a folder that is pushed to a free Docker Space (dashboard public, API private inside the same container). README restructured: "Run it yourself" plus a "Publish a free live demo" section.
- **Why:** A recruiter should see a working product from the README without installing anything. A live link also proves the project was deployed, not only run locally.
- **Design:**
  - A Docker Space needs its own `Dockerfile` and `README.md` (YAML header with `sdk: docker`, `app_port: 7860`) at the root of the Space repository, which differ from this repository's, so the bundle is generated by `deploy/space_bundle.py` from `deploy/space/{Dockerfile,README.md,start.sh}` plus the application code. Not copied: `.git`, `.venv`, `data`, `mlruns`, `tests`, `docs`, `dbt/target`, `dbt/logs`, bytecode caches.
  - The image builds the warehouse and the model with `make pipeline` (synthetic data, about 12 s), so start-up is fast and every deployment serves identical numbers.
  - One public port: `start.sh` starts the API on `127.0.0.1:8010`, waits for `/health` (fails after 60 s), then runs Streamlit on `0.0.0.0:7860` (`API_URL` points to the private API). CORS/XSRF protection of Streamlit are switched off as Spaces serves the app in an iframe behind its proxy.
  - Same non-root uid 1000 as in the Compose image; same `make pipeline` definition.
  - Safety of the generator: it empties an existing bundle but keeps its `.git` (so updates are commit + push) and refuses to touch a non-empty directory that is not a bundle.
  - Deployment itself is manual (push to the Space); no deploy token is stored in CI.
- **Files:** `deploy/{__init__,space_bundle}.py`, `deploy/space/{Dockerfile,README.md,start.sh}`, `tests/test_space_bundle.py` (22 tests), `Makefile`, `pyproject.toml` (mypy covers `deploy`), `.gitignore` (`dist/`), `.dockerignore`, `README.md`.
- **TDD evidence:**
  - RED: `ModuleNotFoundError: No module named 'deploy.space_bundle'`.
  - GREEN: `tests/test_space_bundle.py` -> `22 passed`; `make lint` clean.
  - Local end-to-end check of the bundle: `docker build dist/space` (image 1.63 GB; the build ran `make pipeline`: dbt 35/35, ROC-AUC 0.787), `docker run -p 7860:7860` with only that port published: `/_stcore/health` -> `ok`, the API port is not reachable from the host, process uid 1000, dashboard script executed inside the container showed Customers 5,000 / At risk 961 / churn probability 42.7% and the API log shows the dashboard's calls answered with 200. The test container and the image were removed afterwards.
- **What the tests guarantee:** the bundle has the root files a Docker Space needs, the application code, and none of the local state or dev files; the Space README declares `sdk: docker` and `app_port: 7860` and differs from the GitHub README; the Dockerfile runs `make pipeline`, exposes 7860, runs as non-root and starts `start.sh`; the start script runs the API privately before the public dashboard and waits for `/health`; rebuilding replaces stale files, keeps `.git` and refuses to overwrite a foreign directory.
- **Not verified:** the real deployment on Hugging Face (account, build there, free-tier limits and sleep behaviour were not tested; the app may need about a minute to wake up). The README intentionally has no live link yet: it is added after the owner publishes the Space.

---

## Stage 13b - Public demo on Render (replaces the Hugging Face bundle)

- **Status:** approved
- **What:** `render.yaml` (Render Blueprint: one free Docker web service), `deploy/render/Dockerfile` and `deploy/render/start.sh`. README: "Deploy a free live demo (Render)". The Hugging Face bundle code from Stage 13 was removed (`deploy/space/`, `deploy/space_bundle.py`, its 22 tests, `make space-bundle`); it stays in Git history (commit `d725ea0`).
- **Why:** Stage 13 assumed a free Docker Space. Hugging Face's own documentation says Docker Spaces require a paid plan (PRO) to create; only Static Spaces are free. The assumption was made from memory without checking and was wrong. Render offers a free web service (512 MB RAM, 750 hours a month, spins down after 15 minutes of inactivity; per Render's documentation and articles, no payment method required - not tested by us).
- **Incident that shaped the design:** the owner's first Render deploy built the root `Dockerfile` (made for Compose: no `CMD`, no data, no model). The build succeeded and the log ended with `Application exited early`: Render runs the Dockerfile's `CMD`, the base image's default command exits at once. Fix: a separate demo Dockerfile with `CMD`, built data/model and a start script; the Blueprint points at it; a regression test asserts the `CMD` is present.
- **Design:**
  - Single container, one public port: `start.sh` starts the API on `127.0.0.1:8010`, waits for `/health` (60 s limit), then runs Streamlit on `0.0.0.0:$PORT` (Render provides `PORT`, default 10000). `API_URL` points at the private API.
  - `make pipeline` runs at image build (synthetic data, about 12 s locally), so start-up is fast and every deploy shows identical numbers.
  - Build context is the repository root, no second repository. `.dockerignore` no longer excludes `deploy`; tests check that every `COPY` source exists and is not dockerignored.
  - `render.yaml`: `type: web`, `runtime: docker`, `plan: free`, `dockerfilePath: ./deploy/render/Dockerfile`, `dockerContext: .`, `healthCheckPath: /_stcore/health`, `autoDeployTrigger: commit`.
- **Files:** `render.yaml`, `deploy/render/{Dockerfile,start.sh}`, `tests/test_render_deploy.py` (16 tests), `README.md`, `Makefile`, `pyproject.toml`, `.dockerignore`, `.gitignore`.
- **TDD evidence:**
  - RED: `FileNotFoundError: render.yaml` (and no `deploy/render`).
  - GREEN: `tests/test_render_deploy.py` -> 16 passed; `make test` -> `130 passed`; `make lint` clean.
  - Local check, run like Render runs it (`docker build -f deploy/render/Dockerfile .`, `docker run -e PORT=10000 -p 10000:10000`): `/_stcore/health` -> `ok`, the API port is not reachable from the host, process uid 1000, dashboard script executed in the container showed Customers 5,000 / At risk 961 / churn probability 42.7%, 0 errors in the container log, memory 282 MiB. Test container and image removed afterwards.
- **What the tests guarantee:** the Blueprint declares exactly one free Docker web service with the demo Dockerfile, health check path and auto-deploy; the Dockerfile has a `CMD`, builds data and model, runs as non-root and installs `libgomp1`; every `COPY` source exists in the build context and is not dockerignored; the start script binds `$PORT`, keeps the API private and starts it first, waits for `/health` and is executable; the README documents the Render deployment.
- **Not verified:** the deployment on Render itself. Unknowns: whether the 512 MB free instance has enough memory and time for the image build (`make pipeline` runs during the build), whether Render accepts the Blueprint exactly as written (a summary of the Blueprint spec marked `buildCommand` as required for Docker, which we believe is wrong; the file omits it), and cold-start time after a spin-down (expected about a minute).

---

## Stage 13c - Fix: dashboard crashed on start (`No module named 'services'`)

- **Status:** approved
- **What:** `PYTHONPATH` is now set for every way the dashboard is launched: `ENV PYTHONPATH="/app"` in `Dockerfile` (Compose) and `deploy/render/Dockerfile`, and `PYTHONPATH=. uv run streamlit run ...` in `make dashboard`.
- **Incident:** after the Render deploy the page showed `ModuleNotFoundError: No module named 'services'` (`services/dashboard/app.py`, line 6). `streamlit run <script>` puts the script's folder on `sys.path`, not the project root, and the project is not an installed package. The container health check (`/_stcore/health`) answered `ok` all the time, because Streamlit only executes the script when a browser session connects.
- **Why it was missed (my verification gap):** the dashboard had only been checked with `streamlit.testing.AppTest` (it runs inside pytest, where the project root is already importable) and with the health endpoint. Neither runs the script the way `streamlit run` does, and no launch configuration (`make dashboard`, Compose, Render) had been opened as a real session. The Compose and local launches had the same defect; the "Docker verified" claims in Stages 11 and 13 covered the API and the health endpoint, not the dashboard page.
- **Files:** `Dockerfile`, `deploy/render/Dockerfile`, `Makefile`, `tests/test_dashboard_launch.py` (5 tests).
- **TDD evidence:**
  - RED (reproduced in the built Render image): `docker exec ... python services/dashboard/app.py` -> `ModuleNotFoundError: No module named 'services'`; with `PYTHONPATH=/app` the import passes. Test run: 3 configuration guards failed.
  - GREEN: `tests/test_dashboard_launch.py` -> 5 passed; `make test` and `make lint` clean.
  - Real session check (a small websocket client that opens a Streamlit session like a browser and records rendered elements; kept outside the repo): old behaviour (container started with empty `PYTHONPATH`) -> `ModuleNotFoundError` reported, 0 metrics, while `/_stcore/health` still said `ok` (so the check does detect the bug); fixed Render image, fixed Compose stack and fixed `make dashboard` -> no exceptions, metrics Customers 5,000 / At risk 961 / share 19.2% / revenue at risk 40,239,553 / churn probability 42.7%.
- **What the tests guarantee:** the script cannot import the project without `PYTHONPATH` (documents why it is needed); with it, the script starts in a fresh interpreter and shows the error page instead of crashing when the API is down; the Makefile target and both Dockerfiles set it.
- **Known gap:** there is no permanent end-to-end smoke test of a real dashboard session in CI; the websocket client used above is a candidate for one. Not verified on Render itself until redeployed.

---

## Stage 14 - Dashboard redesign: who to call first (and calibrated probabilities)

- **Status:** approved
- **What:** `GET /portfolio/priority`, a redesigned dashboard, and a model fix (no class reweighting, new `brier` metric).
- **Why:** The owner found the dashboard unclear and weak. A screenshot of the live page showed the real defects: the "Call first" table was empty whenever ENTERPRISE was deselected (the global top 20 was filtered in the browser, so removing the segment with the biggest contracts left nothing); raw column names; a stacked chart in which "at risk" (a subset) looked like an addend; no explanations; and the churn model, the core of the project, was visible only after typing a customer id by hand.
- **Design:**
  - `GET /portfolio/priority?segment=...&limit=` (limit 1-100, default 20, `segment` repeatable): scores all active (not yet churned) customers in one batch, expected loss = churn probability x annual contract value, sorted descending; the response also carries `customers_scored` and `total_expected_loss` over all scored customers, not only the shown rows. 503 without a model. Segment filtering happens on the server, so the top N is always inside the chosen segments.
  - Plain-language signals per customer (`services/api/priority.py`): usage down X% when the 30-day trend ratio is below 0.85 (same threshold as `is_at_risk`), many tickets relative to the segment average (above 1.5x). Customers without a rule-based signal are labelled as model score only.
  - Dashboard: explanatory title and sidebar text, KPIs with tooltips (customers, usage drop count and share, contract value with a usage drop, model expected loss), the ranked table (readable columns, probability progress bar, "Why" column), a customer card that opens on row click (first row by default, no id typing), two single-metric horizontal bar charts per segment. A page-side table builder (`priority_table`) keeps the logic testable.
  - **Model fix found while checking the new numbers:** the Stage 6 model ranked well but its probabilities were inflated (mean prediction 29.9% against 11.7% real churn; customers scored 40-50% churned in 6% of cases) because of `scale_pos_weight`. Money computed from those probabilities was overstated about 2.5x (45.0 M instead of about 16.0 M). Removing the reweighting: hold-out ROC-AUC 0.787 -> 0.796, PR-AUC 0.344 -> 0.339, Brier 0.141 -> 0.090, mean prediction 11.6% vs 11.7% real.
- **Files:** `services/api/{priority,schemas,repository,predictor,main}.py`, `services/dashboard/{app,client,metrics}.py`, `ml/training/train.py`, `tests/test_priority.py` (9), `tests/test_api.py` (+12), `tests/test_dashboard_client.py` (+2), `tests/test_dashboard_metrics.py` (+6), `tests/test_churn_training.py` (+2), `README.md`.
- **TDD evidence:**
  - RED: `ModuleNotFoundError: services.api.priority`; 16 API/client/metrics tests failing on the missing endpoint and methods; calibration tests failed on the old model (`abs(0.226 - 0.1215) < 0.04` false, `KeyError: 'brier'`).
  - GREEN: `make test` -> `168 passed`; `make lint` clean (mypy strict).
  - Live check on the real warehouse (real Streamlit session over websocket plus `AppTest`): no exceptions; table of 20 rows with columns Customer / Segment / Industry / Contract / year / Churn probability / Expected loss / Why. The owner's scenario (ENTERPRISE switched off): 20 rows, all MID_MARKET. Nothing selected: an info message instead of a table. Retrained model: ROC-AUC 0.796, PR-AUC 0.339, Brier 0.090.
- **What the tests guarantee:** ranking is by probability x annual contract value and the total covers everyone scored, not just the top rows; the list never contains churned customers; probabilities in the list equal the single-customer prediction; the server-side segment filter returns a full list even without the segment that owns the biggest contracts (regression test for the empty table); totals follow the filter and equal an independent calculation; invalid segment/limit give 422, no model gives 503; signals text and thresholds; the table has readable columns in a fixed order; mean predicted probability is within 0.04 of the real churn rate and the Brier score beats the base-rate predictor.
- **Known gaps:** the look of the page (spacing, colors) was not seen by me, only structure and content were verified; selecting a row by click was not exercised in an automated session; the model gives only a score, not an explanation, so customers without a rule-based signal show "model score" as the reason (feature attributions such as SHAP would fix this); the high-probability buckets have few customers, so calibration there is less certain; probabilities were checked on the same synthetic data they were trained on (hold-out for the headline metrics, whole table for the calibration table).
