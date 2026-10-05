"""Pure calculations on the API's portfolio summary (no Streamlit, no HTTP)."""

from collections.abc import Sequence
from dataclasses import dataclass

import pandas as pd

from services.api.schemas import (
    PortfolioSummaryOut,
    PriorityCustomerOut,
    Segment,
    SegmentLossOut,
)

SEGMENT_ORDER: list[Segment] = ["SMB", "MID_MARKET", "ENTERPRISE"]
NO_SIGNAL = "no single clear reason, the model sees a combined risk"
PRIORITY_COLUMNS = {
    "customer": "Customer",
    "segment": "Segment",
    "contract": "Annual contract (€)",
    "probability": "Chance of leaving",
    "loss": "Expected loss (€)",
    "why": "Why it is listed",
}


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


def loss_by_segment(items: Sequence[SegmentLossOut], selected: Sequence[str]) -> pd.DataFrame:
    """Expected loss per selected segment in business order; segments without loss show as 0."""
    loss = {item.segment: item.expected_loss for item in items}
    return pd.DataFrame(
        {"segment": name, "expected_loss": loss.get(name, 0.0)}
        for name in SEGMENT_ORDER
        if name in selected
    )


def top_share(customers: Sequence[PriorityCustomerOut], total_expected_loss: float) -> float:
    """Share (0..1) of the total expected loss that the listed customers account for."""
    if total_expected_loss <= 0:
        return 0.0
    return sum(c.expected_loss for c in customers) / total_expected_loss


def format_money(value: float) -> str:
    """Compact euro amount for headlines: 1_234_567 -> '€1.2M', 48_000 -> '€48K', 950 -> '€950'."""
    if value >= 1_000_000:
        return f"€{value / 1_000_000:.1f}M"
    if value >= 10_000:
        return f"€{value / 1_000:.0f}K"
    return f"€{value:,.0f}"


def format_usage_change(usage_trend_ratio: float) -> str:
    """Usage trend ratio as a signed percentage: 0.78 -> '-22%', 1.1 -> '+10%'."""
    return f"{usage_trend_ratio - 1:+.0%}"


def priority_table(customers: Sequence[PriorityCustomerOut]) -> pd.DataFrame:
    """The 'who to call first' table with reader-friendly columns."""
    names = PRIORITY_COLUMNS
    return pd.DataFrame(
        [
            {
                names["customer"]: c.customer_id,
                names["segment"]: c.segment,
                names["contract"]: c.annual_contract_value,
                names["probability"]: c.churn_probability,
                names["loss"]: c.expected_loss,
                names["why"]: "; ".join(c.signals) or NO_SIGNAL,
            }
            for c in customers
        ],
        columns=list(names.values()),
    )
