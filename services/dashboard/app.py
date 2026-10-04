"""Streamlit dashboard. Run with: make dashboard (needs the API: make api)."""

import pandas as pd
import streamlit as st

from services.dashboard.client import ApiClient, ApiUnavailableError
from services.dashboard.metrics import (
    SEGMENT_ORDER,
    at_risk_priority,
    portfolio_kpis,
    segment_summary,
)

PORTFOLIO_LIMIT = 1000  # API maximum


@st.cache_data(ttl=60)
def load_portfolio() -> pd.DataFrame:
    customers = ApiClient.from_env().customers(limit=PORTFOLIO_LIMIT)
    return pd.DataFrame([c.model_dump() for c in customers])


def main() -> None:
    st.set_page_config(page_title="Customer 360", layout="wide")
    st.title("Customer 360")

    try:
        portfolio = load_portfolio()
    except ApiUnavailableError as error:
        st.error(f"{error}. Start the API with `make api`.")
        return
    if portfolio.empty:
        st.warning("The API returned no customers. Run `make pipeline` first.")
        return

    if len(portfolio) >= PORTFOLIO_LIMIT:
        st.caption(
            f"Numbers cover the first {PORTFOLIO_LIMIT:,} customers returned by the API "
            "(its page limit), not necessarily the whole portfolio."
        )

    segments = st.sidebar.multiselect("Segment", SEGMENT_ORDER, default=SEGMENT_ORDER)
    view = portfolio[portfolio["segment"].isin(segments)]

    kpis = portfolio_kpis(view)
    columns = st.columns(4)
    columns[0].metric("Customers", f"{kpis.customers:,}")
    columns[1].metric("At risk", f"{kpis.at_risk:,}")
    columns[2].metric("At-risk share", f"{kpis.at_risk_share:.1%}")
    columns[3].metric("Annual revenue at risk", f"{kpis.annual_revenue_at_risk:,.0f}")

    st.subheader("Segments")
    summary = segment_summary(view)
    st.bar_chart(summary, x="segment", y=["customers", "at_risk"])

    st.subheader("Call first: at-risk customers by contract value")
    st.dataframe(at_risk_priority(view), hide_index=True)

    st.subheader("Customer detail")
    customer_id = st.text_input("Customer id", value="C000000")
    api = ApiClient.from_env()
    customer = api.customer(customer_id)
    if customer is None:
        st.info(f"No customer '{customer_id}'.")
        return
    st.json(customer.model_dump(mode="json"))
    probability = api.predict(customer_id)
    if probability is None:
        st.caption("Churn model is not loaded: train it with `make train`, restart the API.")
    else:
        st.metric("Churn probability", f"{probability:.1%}")


main()
