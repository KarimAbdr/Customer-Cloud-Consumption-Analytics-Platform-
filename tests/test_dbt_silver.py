import os
import subprocess
import sys
from datetime import date
from pathlib import Path

import duckdb
import pytest

from data_platform.ingestion.run import run_ingestion

REPO_ROOT = Path(__file__).resolve().parent.parent
DBT_BIN = Path(sys.executable).parent / "dbt"
N_CUSTOMERS = 60
DAYS = 30

SILVER_COLUMNS = {
    "stg_customers": ["customer_id", "segment", "employees", "industry"],
    "stg_contracts": [
        "customer_id",
        "contract_start_date",
        "contract_end_date",
        "term_months",
        "monthly_fee",
    ],
    "stg_daily_usage": ["customer_id", "usage_date", "daily_usage"],
    "stg_support_tickets": ["customer_id", "ticket_month", "ticket_count"],
    "stg_churn_labels": ["customer_id", "is_churned"],
}


@pytest.fixture(scope="module")
def warehouse(tmp_path_factory: pytest.TempPathFactory) -> Path:
    work = tmp_path_factory.mktemp("dbt_silver")
    bronze = work / "bronze"
    run_ingestion(bronze, n_customers=N_CUSTOMERS, days=DAYS, seed=1, start=date(2025, 1, 6))
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
    return db_path


def _query(db_path: Path, sql: str) -> list[tuple[object, ...]]:
    with duckdb.connect(str(db_path), read_only=True) as con:
        return con.execute(sql).fetchall()


@pytest.mark.parametrize("table", SILVER_COLUMNS)
def test_silver_table_has_expected_columns(warehouse: Path, table: str) -> None:
    rows = _query(
        warehouse,
        f"select column_name from information_schema.columns "
        f"where table_name = '{table}' order by ordinal_position",
    )
    assert [r[0] for r in rows] == SILVER_COLUMNS[table]


def test_row_counts_match_bronze(warehouse: Path) -> None:
    assert _query(warehouse, "select count(*) from stg_customers")[0][0] == N_CUSTOMERS
    assert _query(warehouse, "select count(*) from stg_daily_usage")[0][0] == N_CUSTOMERS * DAYS


def test_missing_industry_is_replaced_with_unknown(warehouse: Path) -> None:
    nulls = _query(warehouse, "select count(*) from stg_customers where industry is null")
    assert nulls[0][0] == 0


def test_usage_date_is_a_date_not_a_timestamp(warehouse: Path) -> None:
    rows = _query(
        warehouse,
        "select data_type from information_schema.columns "
        "where table_name = 'stg_daily_usage' and column_name = 'usage_date'",
    )
    assert rows[0][0] == "DATE"
