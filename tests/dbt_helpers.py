import os
import subprocess
import sys
from datetime import date
from pathlib import Path

import duckdb
import pandas as pd

from data_platform.ingestion.run import build_tables, write_bronze

REPO_ROOT = Path(__file__).resolve().parent.parent
DBT_BIN = Path(sys.executable).parent / "dbt"


def build_warehouse(
    work: Path, n_customers: int, days: int, seed: int
) -> tuple[Path, dict[str, pd.DataFrame]]:
    """Write bronze Parquet, run `dbt build` into a temp DuckDB, return its path and bronze."""
    tables = build_tables(n_customers, days, seed, date(2025, 1, 6))
    bronze = work / "bronze"
    write_bronze(tables, bronze)
    db_path = work / "warehouse.duckdb"
    env = {
        **os.environ,
        "BRONZE_DIR": str(bronze),
        "DUCKDB_PATH": str(db_path),
        "DBT_TARGET_PATH": str(work / "target"),
        "DBT_LOG_PATH": str(work / "logs"),
    }
    result = subprocess.run(
        [str(DBT_BIN), "build", "--project-dir", "dbt", "--profiles-dir", "dbt"],
        cwd=REPO_ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    return db_path, tables


def query(db_path: Path, sql: str) -> list[tuple[object, ...]]:
    with duckdb.connect(str(db_path), read_only=True) as con:
        return con.execute(sql).fetchall()
