"""Who to call first: customers ranked by expected revenue loss.

Expected loss = churn probability x annual contract value, so a likely loss of a large contract
outranks a near-certain loss of a tiny one.
"""

import numpy as np
import pandas as pd

from services.api.schemas import PriorityCustomerOut, PriorityListOut

# Same threshold as `is_at_risk` in the gold layer (usage_trend_ratio < 0.85).
USAGE_DROP_THRESHOLD = 0.85
TICKET_FACTOR = 1.5


def explain(usage_trend_ratio: float, total_tickets: int, segment_avg_tickets: float) -> list[str]:
    """Plain-language reasons a customer looks risky (the model score has no explanation)."""
    signals: list[str] = []
    if usage_trend_ratio < USAGE_DROP_THRESHOLD:
        drop = round((1 - usage_trend_ratio) * 100)
        signals.append(f"usage down {drop}% (last 30 days vs first 30)")
    if segment_avg_tickets > 0 and total_tickets > TICKET_FACTOR * segment_avg_tickets:
        factor = total_tickets / segment_avg_tickets
        signals.append(f"{total_tickets} support tickets ({factor:.1f}x segment average)")
    return signals


def build_priority(active: pd.DataFrame, probabilities: np.ndarray, limit: int) -> PriorityListOut:
    """Rank `active` customers (features table) by expected loss; the total covers all of them."""
    frame = active.assign(
        churn_probability=probabilities, annual_contract_value=active["monthly_fee"] * 12
    )
    frame["expected_loss"] = frame["churn_probability"] * frame["annual_contract_value"]
    frame["segment_avg_tickets"] = frame.groupby("segment")["total_tickets"].transform("mean")
    top = frame.sort_values(["expected_loss", "customer_id"], ascending=[False, True]).head(limit)
    items = [
        PriorityCustomerOut(
            customer_id=str(row["customer_id"]),
            segment=row["segment"],
            industry=str(row["industry"]),
            employees=int(row["employees"]),
            annual_contract_value=float(row["annual_contract_value"]),
            churn_probability=float(row["churn_probability"]),
            expected_loss=float(row["expected_loss"]),
            usage_trend_ratio=float(row["usage_trend_ratio"]),
            total_tickets=int(row["total_tickets"]),
            signals=explain(
                float(row["usage_trend_ratio"]),
                int(row["total_tickets"]),
                float(row["segment_avg_tickets"]),
            ),
        )
        for row in top.to_dict("records")
    ]
    return PriorityListOut(
        customers_scored=len(frame),
        total_expected_loss=float(frame["expected_loss"].sum()),
        items=items,
    )
