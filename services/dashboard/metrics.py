"""Pure calculations on the API's portfolio summary (no Streamlit, no HTTP)."""

from collections.abc import Sequence
from dataclasses import dataclass

import pandas as pd

from services.api.schemas import PortfolioSummaryOut

SEGMENT_ORDER = ["SMB", "MID_MARKET", "ENTERPRISE"]


@dataclass(frozen=True)
class PortfolioKpis:
    customers: int
    at_risk: int
    at_risk_share: float
    annual_revenue_at_risk: float


def segment_frame(summary: PortfolioSummaryOut) -> pd.DataFrame:
    """One row per segment in business order."""
    frame = pd.DataFrame(
        [s.model_dump() for s in summary.segments],
        columns=["segment", "customers", "at_risk", "annual_revenue_at_risk"],
    )
    rank = frame["segment"].map({name: i for i, name in enumerate(SEGMENT_ORDER)})
    return (
        frame.assign(_rank=rank).sort_values("_rank").drop(columns="_rank").reset_index(drop=True)
    )


def kpis_for(segments: pd.DataFrame, selected: Sequence[str]) -> PortfolioKpis:
    """KPIs of the chosen segments; the summary is already aggregated server-side."""
    chosen = segments[segments["segment"].isin(selected)]
    customers = int(chosen["customers"].sum())
    at_risk = int(chosen["at_risk"].sum())
    return PortfolioKpis(
        customers=customers,
        at_risk=at_risk,
        at_risk_share=at_risk / customers if customers else 0.0,
        annual_revenue_at_risk=float(chosen["annual_revenue_at_risk"].sum()),
    )
