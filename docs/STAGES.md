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
