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
