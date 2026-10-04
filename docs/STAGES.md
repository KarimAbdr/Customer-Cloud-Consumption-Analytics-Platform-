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
  - Full run (`make pipeline`, 5000 customers): ROC-AUC 0.787, PR-AUC 0.344 (churn base rate about 11.7%).
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
- **README placeholder:** the CI badge URL contains `OWNER/REPO`; replace it after creating the GitHub repository.
