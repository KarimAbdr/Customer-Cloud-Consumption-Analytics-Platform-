import pandas as pd
import pytest

from services.dashboard.metrics import at_risk_priority, portfolio_kpis, segment_summary


def _customers() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "customer_id": ["A", "B", "C", "D"],
            "segment": ["SMB", "SMB", "ENTERPRISE", "ENTERPRISE"],
            "annual_contract_value": [1_000.0, 3_000.0, 50_000.0, 70_000.0],
            "is_at_risk": [True, False, True, False],
            "is_churned": [False, False, True, False],
        }
    )


def test_kpis_count_customers_and_at_risk_share() -> None:
    kpis = portfolio_kpis(_customers())
    assert kpis.customers == 4
    assert kpis.at_risk == 2
    assert kpis.at_risk_share == 0.5


def test_kpis_sum_revenue_at_risk() -> None:
    assert portfolio_kpis(_customers()).annual_revenue_at_risk == 51_000.0


def test_kpis_on_empty_portfolio_are_zero_not_an_error() -> None:
    kpis = portfolio_kpis(_customers().iloc[0:0])
    assert (kpis.customers, kpis.at_risk, kpis.at_risk_share) == (0, 0, 0.0)
    assert kpis.annual_revenue_at_risk == 0.0


def test_segment_summary_has_one_row_per_segment() -> None:
    summary = segment_summary(_customers()).set_index("segment")
    assert summary.loc["SMB", "customers"] == 2
    assert summary.loc["ENTERPRISE", "at_risk"] == 1
    assert summary.loc["ENTERPRISE", "annual_contract_value"] == 120_000.0


def test_segment_summary_uses_business_order_not_alphabet() -> None:
    assert list(segment_summary(_customers())["segment"]) == ["SMB", "ENTERPRISE"]


def test_at_risk_priority_lists_only_at_risk_biggest_contract_first() -> None:
    ranked = at_risk_priority(_customers())
    assert list(ranked["customer_id"]) == ["C", "A"]


@pytest.mark.parametrize("top", [1, 5])
def test_at_risk_priority_respects_top(top: int) -> None:
    assert len(at_risk_priority(_customers(), top=top)) == min(top, 2)
