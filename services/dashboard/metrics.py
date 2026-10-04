"""Pure calculations on the API's portfolio summary (no Streamlit, no HTTP)."""

from collections.abc import Sequence
from dataclasses import dataclass

import pandas as pd

from services.api.schemas import PortfolioSummaryOut, PriorityCustomerOut, Segment

SEGMENT_ORDER: list[Segment] = ["SMB", "MID_MARKET", "ENTERPRISE"]
NO_SIGNAL = "no single dominant signal (model score)"


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
    frame["at_risk_share"] = (frame["at_risk"] / frame["customers"] * 100).fillna(0.0)
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


def priority_table(customers: Sequence[PriorityCustomerOut]) -> pd.DataFrame:
    """The 'who to call first' table with reader-friendly columns."""
    return pd.DataFrame(
        [
            {
                "Customer": c.customer_id,
                "Segment": c.segment,
                "Industry": c.industry,
                "Contract / year": c.annual_contract_value,
                "Churn probability": c.churn_probability,
                "Expected loss": c.expected_loss,
                "Why": "; ".join(c.signals) or NO_SIGNAL,
            }
            for c in customers
        ],
        columns=[
            "Customer",
            "Segment",
            "Industry",
            "Contract / year",
            "Churn probability",
            "Expected loss",
            "Why",
        ],
    )
