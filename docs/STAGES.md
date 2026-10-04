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
