import pandas as pd

from services.api.schemas import PortfolioSummaryOut, PriorityCustomerOut, SegmentSummaryOut
from services.dashboard.metrics import NO_SIGNAL, kpis_for, priority_table, segment_frame


def _summary() -> PortfolioSummaryOut:
    return PortfolioSummaryOut(
        customers=10,
        at_risk=3,
        at_risk_share=0.3,
        annual_revenue_at_risk=51_000.0,
        segments=[
            SegmentSummaryOut(
                segment="ENTERPRISE", customers=2, at_risk=1, annual_revenue_at_risk=50_000.0
            ),
            SegmentSummaryOut(
                segment="SMB", customers=8, at_risk=2, annual_revenue_at_risk=1_000.0
            ),
        ],
    )


def test_segment_frame_uses_business_order_not_alphabet_or_api_order() -> None:
    assert list(segment_frame(_summary())["segment"]) == ["SMB", "ENTERPRISE"]


def test_kpis_for_all_segments_add_up_to_the_portfolio() -> None:
    kpis = kpis_for(segment_frame(_summary()), ["SMB", "ENTERPRISE"])
    assert (kpis.customers, kpis.at_risk) == (10, 3)
    assert kpis.annual_revenue_at_risk == 51_000.0
    assert kpis.at_risk_share == 0.3


def test_kpis_for_a_segment_selection_only_count_that_selection() -> None:
    kpis = kpis_for(segment_frame(_summary()), ["ENTERPRISE"])
    assert (kpis.customers, kpis.at_risk) == (2, 1)
    assert kpis.at_risk_share == 0.5
    assert kpis.annual_revenue_at_risk == 50_000.0


def test_kpis_for_an_empty_selection_are_zero_not_an_error() -> None:
    kpis = kpis_for(segment_frame(_summary()), [])
    assert (kpis.customers, kpis.at_risk, kpis.at_risk_share) == (0, 0, 0.0)
    assert kpis.annual_revenue_at_risk == 0.0


def test_segment_frame_of_an_empty_portfolio_is_an_empty_frame() -> None:
    empty = PortfolioSummaryOut(
        customers=0, at_risk=0, at_risk_share=0.0, annual_revenue_at_risk=0.0, segments=[]
    )
    frame = segment_frame(empty)
    assert isinstance(frame, pd.DataFrame)
    assert frame.empty


def test_segment_frame_has_the_share_of_customers_at_risk_in_percent() -> None:
    frame = segment_frame(_summary()).set_index("segment")
    assert frame.loc["SMB", "at_risk_share"] == 25.0
    assert frame.loc["ENTERPRISE", "at_risk_share"] == 50.0


def _customer(customer_id: str, signals: list[str]) -> PriorityCustomerOut:
    return PriorityCustomerOut(
        customer_id=customer_id,
        segment="ENTERPRISE",
        industry="Retail",
        employees=100,
        annual_contract_value=120_000.0,
        churn_probability=0.4,
        expected_loss=48_000.0,
        usage_trend_ratio=0.8,
        total_tickets=3,
        signals=signals,
    )


def test_priority_table_uses_readable_column_names_in_a_fixed_order() -> None:
    table = priority_table([_customer("C1", ["usage down 20%"])])
    assert list(table.columns) == [
        "Customer",
        "Segment",
        "Industry",
        "Contract / year",
        "Churn probability",
        "Expected loss",
        "Why",
    ]


def test_priority_table_joins_signals_into_one_readable_cell() -> None:
    table = priority_table([_customer("C1", ["usage down 20%", "30 support tickets"])])
    assert table.loc[0, "Why"] == "usage down 20%; 30 support tickets"


def test_priority_table_says_so_when_there_is_no_single_signal() -> None:
    assert priority_table([_customer("C1", [])]).loc[0, "Why"] == NO_SIGNAL


def test_priority_table_keeps_the_probability_between_zero_and_one() -> None:
    assert priority_table([_customer("C1", [])]).loc[0, "Churn probability"] == 0.4


def test_priority_table_of_nobody_is_an_empty_table_with_the_same_columns() -> None:
    table = priority_table([])
    assert table.empty
    assert "Customer" in table.columns
