"""Pure portfolio calculations for the dashboard (no Streamlit, no HTTP)."""

from dataclasses import dataclass

import pandas as pd

SEGMENT_ORDER = ["SMB", "MID_MARKET", "ENTERPRISE"]


@dataclass(frozen=True)
class PortfolioKpis:
    customers: int
    at_risk: int
    at_risk_share: float
    annual_revenue_at_risk: float


def portfolio_kpis(customers: pd.DataFrame) -> PortfolioKpis:
    at_risk = customers[customers["is_at_risk"]]
    total = len(customers)
    return PortfolioKpis(
        customers=total,
        at_risk=len(at_risk),
        at_risk_share=len(at_risk) / total if total else 0.0,
        annual_revenue_at_risk=float(at_risk["annual_contract_value"].sum()),
    )


def segment_summary(customers: pd.DataFrame) -> pd.DataFrame:
    grouped = customers.groupby("segment", as_index=False).agg(
        customers=("customer_id", "count"),
        at_risk=("is_at_risk", "sum"),
        annual_contract_value=("annual_contract_value", "sum"),
    )
    grouped["segment"] = pd.Categorical(grouped["segment"], categories=SEGMENT_ORDER, ordered=True)
    ordered = grouped.sort_values("segment").reset_index(drop=True)
    ordered["segment"] = ordered["segment"].astype(str)
    return ordered


def at_risk_priority(customers: pd.DataFrame, top: int = 20) -> pd.DataFrame:
    """At-risk customers, biggest contract first: who to call first."""
    at_risk = customers[customers["is_at_risk"]]
    return at_risk.sort_values("annual_contract_value", ascending=False).head(top)
