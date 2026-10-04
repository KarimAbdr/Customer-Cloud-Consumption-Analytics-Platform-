from datetime import date

import numpy as np
import pandas as pd
import pytest

from data_platform.ingestion.synthetic import (
    generate_churn_labels,
    generate_contracts,
    generate_customers,
    generate_dissatisfaction,
    generate_tickets,
    generate_usage,
)

SEED = 7
START = date(2025, 1, 6)
DAYS = 140
MONTHS = 6


@pytest.fixture(scope="module")
def customers() -> pd.DataFrame:
    return generate_customers(n=2_000, seed=SEED)


@pytest.fixture(scope="module")
def dissatisfaction(customers: pd.DataFrame) -> np.ndarray:
    return generate_dissatisfaction(n=len(customers), seed=SEED)


@pytest.fixture(scope="module")
def tickets(customers: pd.DataFrame, dissatisfaction: np.ndarray) -> pd.DataFrame:
    return generate_tickets(
        customers, start=START, months=MONTHS, seed=SEED, dissatisfaction=dissatisfaction
    )


@pytest.fixture(scope="module")
def usage(customers: pd.DataFrame, dissatisfaction: np.ndarray) -> pd.DataFrame:
    return generate_usage(
        customers, start=START, days=DAYS, seed=SEED, dissatisfaction=dissatisfaction
    )


@pytest.fixture(scope="module")
def churn(customers: pd.DataFrame, dissatisfaction: np.ndarray) -> pd.DataFrame:
    contracts = generate_contracts(customers, seed=SEED)
    return generate_churn_labels(customers, contracts, dissatisfaction=dissatisfaction, seed=SEED)


def test_dissatisfaction_is_deterministic_for_same_seed() -> None:
    np.testing.assert_array_equal(
        generate_dissatisfaction(n=50, seed=SEED), generate_dissatisfaction(n=50, seed=SEED)
    )


def test_tickets_are_deterministic_for_same_seed(
    customers: pd.DataFrame, dissatisfaction: np.ndarray
) -> None:
    small = customers.head(50)
    first = generate_tickets(small, START, MONTHS, SEED, dissatisfaction[:50])
    second = generate_tickets(small, START, MONTHS, SEED, dissatisfaction[:50])
    pd.testing.assert_frame_equal(first, second)


def test_tickets_have_one_row_per_customer_per_month(
    customers: pd.DataFrame, tickets: pd.DataFrame
) -> None:
    assert len(tickets) == len(customers) * MONTHS
    assert not tickets.duplicated(["customer_id", "month"]).any()
    assert set(tickets["customer_id"]) == set(customers["customer_id"])


def test_ticket_counts_are_non_negative_integers(tickets: pd.DataFrame) -> None:
    assert pd.api.types.is_integer_dtype(tickets["ticket_count"])
    assert (tickets["ticket_count"] >= 0).all()


def test_enterprise_customers_open_more_tickets_than_smb(
    customers: pd.DataFrame, tickets: pd.DataFrame
) -> None:
    merged = tickets.merge(customers[["customer_id", "segment"]], on="customer_id")
    mean_tickets = merged.groupby("segment")["ticket_count"].mean()
    assert mean_tickets["ENTERPRISE"] > mean_tickets["SMB"]


def test_churn_share_is_realistic(churn: pd.DataFrame) -> None:
    assert 0.08 <= churn["churned"].mean() <= 0.15


def test_churn_labels_are_binary_and_one_per_customer(
    customers: pd.DataFrame, churn: pd.DataFrame
) -> None:
    assert set(churn["churned"].unique()) <= {0, 1}
    assert churn["customer_id"].is_unique
    assert set(churn["customer_id"]) == set(customers["customer_id"])


def test_churned_customers_open_more_tickets(tickets: pd.DataFrame, churn: pd.DataFrame) -> None:
    per_customer = tickets.groupby("customer_id")["ticket_count"].sum().rename("total")
    merged = churn.merge(per_customer, on="customer_id")
    by_label = merged.groupby("churned")["total"].mean()
    assert by_label[1] > by_label[0]


def test_churned_customers_have_worse_usage_trend(usage: pd.DataFrame, churn: pd.DataFrame) -> None:
    ordered = usage.sort_values(["customer_id", "usage_date"])
    grouped = ordered.groupby("customer_id")["daily_usage"]
    first = grouped.apply(lambda s: s.iloc[:28].mean())
    last = grouped.apply(lambda s: s.iloc[-28:].mean())
    ratio = (last / first).rename("ratio")
    merged = churn.merge(ratio, on="customer_id")
    by_label = merged.groupby("churned")["ratio"].median()
    assert by_label[1] < by_label[0]


def test_latent_dissatisfaction_is_not_leaked_into_tables(
    tickets: pd.DataFrame, usage: pd.DataFrame, churn: pd.DataFrame
) -> None:
    for table in (tickets, usage, churn):
        assert not any("dissatisf" in c or "latent" in c for c in table.columns)


def test_empty_inputs_return_empty_tables_with_same_columns(
    tickets: pd.DataFrame, churn: pd.DataFrame
) -> None:
    empty = generate_customers(n=0, seed=SEED)
    no_dissatisfaction = generate_dissatisfaction(n=0, seed=SEED)
    empty_tickets = generate_tickets(empty, START, MONTHS, SEED, no_dissatisfaction)
    empty_churn = generate_churn_labels(
        empty, generate_contracts(empty, seed=SEED), no_dissatisfaction, SEED
    )
    assert empty_tickets.empty
    assert list(empty_tickets.columns) == list(tickets.columns)
    assert empty_churn.empty
    assert list(empty_churn.columns) == list(churn.columns)
