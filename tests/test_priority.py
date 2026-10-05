import numpy as np
import pandas as pd
import pytest

from services.api.priority import build_priority, explain


def _active() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "customer_id": ["A", "B", "C", "D"],
            "segment": ["SMB", "SMB", "ENTERPRISE", "ENTERPRISE"],
            "industry": ["Retail", "Retail", "Technology", "Technology"],
            "employees": [10, 20, 5000, 8000],
            "monthly_fee": [100.0, 200.0, 10_000.0, 5_000.0],
            "usage_trend_ratio": [0.70, 1.00, 0.95, 0.80],
            "total_tickets": [1, 1, 40, 10],
        }
    )


def test_ranks_by_probability_times_annual_contract_value() -> None:
    # annual value: A 1,200  B 2,400  C 120,000  D 60,000
    result = build_priority(_active(), np.array([0.9, 0.5, 0.2, 0.5]), limit=10)
    assert [c.customer_id for c in result.items] == ["D", "C", "B", "A"]


def test_expected_loss_is_probability_times_annual_contract_value() -> None:
    result = build_priority(_active(), np.array([0.9, 0.5, 0.2, 0.5]), limit=10)
    by_id = {c.customer_id: c for c in result.items}
    assert by_id["D"].annual_contract_value == 60_000.0
    assert by_id["D"].expected_loss == pytest.approx(30_000.0)
    assert by_id["A"].expected_loss == pytest.approx(1_080.0)


def test_limit_cuts_the_list_but_not_the_total() -> None:
    result = build_priority(_active(), np.array([0.9, 0.5, 0.2, 0.5]), limit=2)
    assert len(result.items) == 2
    assert result.customers_scored == 4
    assert result.total_expected_loss == pytest.approx(1_080 + 1_200 + 24_000 + 30_000)


def test_empty_population_gives_an_empty_list_and_zero_total() -> None:
    result = build_priority(_active().iloc[0:0], np.array([]), limit=5)
    assert result.items == []
    assert (result.customers_scored, result.total_expected_loss) == (0, 0.0)


def test_signals_are_attached_to_each_customer() -> None:
    result = build_priority(_active(), np.array([0.9, 0.5, 0.2, 0.5]), limit=10)
    signals = {c.customer_id: c.signals for c in result.items}
    assert any("usage" in s for s in signals["A"])
    assert signals["B"] == []


def test_usage_drop_is_reported_in_percent() -> None:
    assert explain(0.81, 1, 1.0) == ["usage down 19% vs. the start of the period"]


def test_usage_above_the_threshold_is_not_a_signal() -> None:
    assert explain(0.86, 1, 1.0) == []


def test_many_tickets_are_compared_with_the_segment_average() -> None:
    assert explain(1.0, 30, 10.0) == ["30 support tickets, 3.0x the segment average"]


def test_usage_signal_comes_before_tickets() -> None:
    signals = explain(0.5, 30, 10.0)
    assert signals[0].startswith("usage down 50%")
    assert len(signals) == 2


def test_zero_segment_average_does_not_divide_by_zero() -> None:
    assert explain(1.0, 5, 0.0) == []


def test_by_segment_sums_expected_loss_per_segment_and_adds_up_to_the_total() -> None:
    result = build_priority(_active(), np.array([0.9, 0.5, 0.2, 0.5]), limit=1)
    by_segment = {s.segment: s.expected_loss for s in result.by_segment}
    assert by_segment["SMB"] == pytest.approx(1_080 + 1_200)
    assert by_segment["ENTERPRISE"] == pytest.approx(24_000 + 30_000)
    assert sum(by_segment.values()) == pytest.approx(result.total_expected_loss)
