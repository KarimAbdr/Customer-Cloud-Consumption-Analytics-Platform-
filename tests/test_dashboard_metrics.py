import pandas as pd

from services.api.schemas import PortfolioSummaryOut, SegmentSummaryOut
from services.dashboard.metrics import kpis_for, segment_frame


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
