import pandas as pd

from services.api.schemas import (
    PortfolioSummaryOut,
    PriorityCustomerOut,
    SegmentLossOut,
    SegmentSummaryOut,
)
from services.dashboard.metrics import (
    NO_SIGNAL,
    format_money,
    format_usage_change,
    kpis_for,
    loss_by_segment,
    priority_table,
    segment_frame,
    top_share,
)


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
        "Annual contract (€)",
        "Chance of leaving",
        "Expected loss (€)",
        "Why it is listed",
    ]


def test_priority_table_joins_signals_into_one_readable_cell() -> None:
    table = priority_table([_customer("C1", ["usage down 20%", "30 support tickets"])])
    assert table.loc[0, "Why it is listed"] == "usage down 20%; 30 support tickets"


def test_priority_table_says_so_when_there_is_no_single_signal() -> None:
    assert priority_table([_customer("C1", [])]).loc[0, "Why it is listed"] == NO_SIGNAL


def test_priority_table_keeps_the_probability_between_zero_and_one() -> None:
    assert priority_table([_customer("C1", [])]).loc[0, "Chance of leaving"] == 0.4


def test_priority_table_of_nobody_is_an_empty_table_with_the_same_columns() -> None:
    table = priority_table([])
    assert table.empty
    assert "Customer" in table.columns


def test_top_share_is_the_listed_loss_over_the_total_loss() -> None:
    customers = [_customer("C1", []), _customer("C2", [])]  # 48_000 each
    assert top_share(customers, 192_000.0) == 0.5


def test_top_share_of_a_zero_total_is_zero_not_a_division_error() -> None:
    assert top_share([_customer("C1", [])], 0.0) == 0.0
    assert top_share([], 0.0) == 0.0


def test_loss_by_segment_is_in_business_order_and_filtered_to_the_selection() -> None:
    items = [
        SegmentLossOut(segment="ENTERPRISE", expected_loss=500.0),
        SegmentLossOut(segment="SMB", expected_loss=100.0),
    ]
    frame = loss_by_segment(items, ["ENTERPRISE", "SMB"])
    assert list(frame["segment"]) == ["SMB", "ENTERPRISE"]
    assert list(loss_by_segment(items, ["SMB"])["segment"]) == ["SMB"]


def test_loss_by_segment_shows_a_selected_segment_without_loss_as_zero() -> None:
    frame = loss_by_segment([], ["MID_MARKET"])
    assert frame.loc[0, "expected_loss"] == 0.0


def test_format_money_is_compact_and_uses_euro() -> None:
    assert format_money(1_234_567) == "€1.2M"
    assert format_money(48_000) == "€48K"
    assert format_money(950) == "€950"
    assert format_money(0) == "€0"


def test_format_usage_change_is_signed() -> None:
    assert format_usage_change(0.78) == "-22%"
    assert format_usage_change(1.1) == "+10%"
    assert format_usage_change(1.0) == "+0%"
