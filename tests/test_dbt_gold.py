from pathlib import Path

import pandas as pd
import pytest

from tests.dbt_helpers import build_warehouse, query

N_CUSTOMERS = 60
DAYS = 60
WINDOW = 30

FEATURE_COLUMNS = [
    "customer_id",
    "segment",
    "employees",
    "industry",
    "term_months",
    "monthly_fee",
    "usage_first_30d_avg",
    "usage_last_30d_avg",
    "usage_trend_ratio",
    "weekend_usage_share",
    "usage_peak_ratio",
    "total_tickets",
    "avg_monthly_tickets",
    "is_churned",
]
CUSTOMER_360_COLUMNS = [
    "customer_id",
    "segment",
    "employees",
    "industry",
    "contract_end_date",
    "annual_contract_value",
    "avg_daily_usage",
    "usage_trend_ratio",
    "total_tickets",
    "is_at_risk",
    "is_churned",
]


@pytest.fixture(scope="module")
def built(tmp_path_factory: pytest.TempPathFactory) -> tuple[Path, dict[str, pd.DataFrame]]:
    return build_warehouse(tmp_path_factory.mktemp("dbt_gold"), N_CUSTOMERS, DAYS, seed=2)


def _columns(db_path: Path, table: str) -> list[object]:
    rows = query(
        db_path,
        f"select column_name from information_schema.columns "
        f"where table_name = '{table}' order by ordinal_position",
    )
    return [r[0] for r in rows]


def test_customer_features_has_expected_columns(built: tuple[Path, object]) -> None:
    assert _columns(built[0], "customer_features") == FEATURE_COLUMNS


def test_customer_360_has_expected_columns(built: tuple[Path, object]) -> None:
    assert _columns(built[0], "customer_360") == CUSTOMER_360_COLUMNS


def test_one_row_per_customer(built: tuple[Path, object]) -> None:
    for table in ("customer_features", "customer_360"):
        total, distinct = query(
            built[0], f"select count(*), count(distinct customer_id) from {table}"
        )[0]
        assert total == distinct == N_CUSTOMERS


def test_numeric_features_have_no_nulls(built: tuple[Path, object]) -> None:
    checks = " or ".join(f"{c} is null" for c in FEATURE_COLUMNS if c != "industry")
    assert query(built[0], f"select count(*) from customer_features where {checks}")[0][0] == 0


def test_features_match_independent_pandas_computation(
    built: tuple[Path, dict[str, pd.DataFrame]],
) -> None:
    db_path, tables = built
    usage = tables["daily_usage"].sort_values(["customer_id", "usage_date"])
    tickets = tables["support_tickets"]
    for customer_id in tables["customers"]["customer_id"].head(5):
        series = usage.loc[usage["customer_id"] == customer_id, "daily_usage"]
        first, last = series.head(WINDOW).mean(), series.tail(WINDOW).mean()
        customer_tickets = tickets.loc[tickets["customer_id"] == customer_id, "ticket_count"]
        row = query(
            db_path,
            "select usage_first_30d_avg, usage_last_30d_avg, usage_trend_ratio, "
            "usage_peak_ratio, total_tickets, avg_monthly_tickets "
            f"from customer_features where customer_id = '{customer_id}'",
        )[0]
        expected = (
            first,
            last,
            last / first,
            series.max() / series.mean(),
            customer_tickets.sum(),
            customer_tickets.mean(),
        )
        assert row == pytest.approx(expected, rel=1e-6)


def test_churn_rate_matches_silver(built: tuple[Path, object]) -> None:
    gold = query(built[0], "select avg(is_churned::int) from customer_features")[0][0]
    silver = query(built[0], "select avg(is_churned::int) from stg_churn_labels")[0][0]
    assert gold == pytest.approx(silver)


def test_at_risk_flag_follows_usage_trend(built: tuple[Path, object]) -> None:
    mismatches = query(
        built[0],
        "select count(*) from customer_360 where is_at_risk != (usage_trend_ratio < 0.85)",
    )[0][0]
    assert mismatches == 0
