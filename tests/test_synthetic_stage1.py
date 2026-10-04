from datetime import date

import pandas as pd
import pytest

from data_platform.ingestion.synthetic import (
    generate_contracts,
    generate_customers,
    generate_usage,
)

SEED = 42
START = date(2025, 1, 6)  # a Monday


@pytest.fixture(scope="module")
def customers() -> pd.DataFrame:
    return generate_customers(n=2_000, seed=SEED)


@pytest.fixture(scope="module")
def usage(customers: pd.DataFrame) -> pd.DataFrame:
    return generate_usage(customers.head(200), start=START, days=140, seed=SEED)


def test_customers_are_deterministic_for_same_seed() -> None:
    first = generate_customers(n=100, seed=SEED)
    second = generate_customers(n=100, seed=SEED)
    pd.testing.assert_frame_equal(first, second)


def test_customers_differ_for_different_seeds() -> None:
    first = generate_customers(n=100, seed=1)
    second = generate_customers(n=100, seed=2)
    assert not first["employees"].equals(second["employees"])


def test_customer_ids_are_unique(customers: pd.DataFrame) -> None:
    assert customers["customer_id"].is_unique


def test_zero_customers_returns_empty_frame_with_same_columns(customers: pd.DataFrame) -> None:
    empty = generate_customers(n=0, seed=SEED)
    assert empty.empty
    assert list(empty.columns) == list(customers.columns)


def test_employees_are_right_skewed(customers: pd.DataFrame) -> None:
    employees = customers["employees"]
    assert employees.mean() > 1.5 * employees.median()
    assert employees.min() >= 1


def test_segment_mix_is_realistic(customers: pd.DataFrame) -> None:
    share = customers["segment"].value_counts(normalize=True)
    assert 0.50 <= share["SMB"] <= 0.70
    assert 0.20 <= share["MID_MARKET"] <= 0.40
    assert 0.05 <= share["ENTERPRISE"] <= 0.15


def test_enterprise_customers_are_larger_than_smb(customers: pd.DataFrame) -> None:
    median_size = customers.groupby("segment")["employees"].median()
    assert median_size["ENTERPRISE"] > median_size["MID_MARKET"] > median_size["SMB"]


def test_optional_fields_have_small_share_of_nulls(customers: pd.DataFrame) -> None:
    null_share = customers["industry"].isna().mean()
    assert 0.01 <= null_share <= 0.10


def test_each_customer_has_exactly_one_contract(customers: pd.DataFrame) -> None:
    contracts = generate_contracts(customers, seed=SEED)
    assert contracts["customer_id"].is_unique
    assert set(contracts["customer_id"]) == set(customers["customer_id"])


def test_contract_end_is_after_start(customers: pd.DataFrame) -> None:
    contracts = generate_contracts(customers, seed=SEED)
    assert (contracts["end_date"] > contracts["start_date"]).all()


def test_usage_references_only_existing_customers(
    customers: pd.DataFrame, usage: pd.DataFrame
) -> None:
    assert set(usage["customer_id"]).issubset(set(customers["customer_id"]))


def test_usage_has_one_row_per_customer_per_day(usage: pd.DataFrame) -> None:
    assert not usage.duplicated(["customer_id", "usage_date"]).any()
    assert len(usage) == 200 * 140


def test_usage_is_lower_on_weekends(usage: pd.DataFrame) -> None:
    weekday = pd.to_datetime(usage["usage_date"]).dt.dayofweek
    weekend_mean = usage.loc[weekday >= 5, "daily_usage"].mean()
    weekday_mean = usage.loc[weekday < 5, "daily_usage"].mean()
    assert weekend_mean < 0.8 * weekday_mean


def test_usage_values_are_diverse_and_non_negative(usage: pd.DataFrame) -> None:
    assert (usage["daily_usage"] >= 0).all()
    assert usage["daily_usage"].nunique() / len(usage) > 0.95
