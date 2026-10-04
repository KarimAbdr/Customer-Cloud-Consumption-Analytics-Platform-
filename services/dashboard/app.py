"""Streamlit dashboard. Run with: make dashboard (needs the API: make api)."""

import pandas as pd
import streamlit as st

from services.api.schemas import CustomerOut, PortfolioSummaryOut
from services.dashboard.client import ApiClient, ApiUnavailableError
from services.dashboard.metrics import SEGMENT_ORDER, kpis_for, segment_frame

TOP_AT_RISK = 20


@st.cache_data(ttl=60)
def load_summary() -> PortfolioSummaryOut:
    return ApiClient.from_env().summary()


@st.cache_data(ttl=60)
def load_priority_list() -> list[CustomerOut]:
    """At-risk customers across the whole portfolio, biggest contract first."""
    return ApiClient.from_env().customers(at_risk=True, order="value", limit=TOP_AT_RISK)


def main() -> None:
    st.set_page_config(page_title="Customer 360", layout="wide")
    st.title("Customer 360")

    try:
        summary = load_summary()
        priority = load_priority_list()
    except ApiUnavailableError as error:
        st.error(f"{error}. Start the API with `make api`.")
        return
    if summary.customers == 0:
        st.warning("The portfolio is empty. Run `make pipeline` first.")
        return

    selected = st.sidebar.multiselect("Segment", SEGMENT_ORDER, default=SEGMENT_ORDER)
    segments = segment_frame(summary)

    kpis = kpis_for(segments, selected)
    columns = st.columns(4)
    columns[0].metric("Customers", f"{kpis.customers:,}")
    columns[1].metric("At risk", f"{kpis.at_risk:,}")
    columns[2].metric("At-risk share", f"{kpis.at_risk_share:.1%}")
    columns[3].metric("Annual revenue at risk", f"{kpis.annual_revenue_at_risk:,.0f}")

    st.subheader("Segments")
    st.bar_chart(
        segments[segments["segment"].isin(selected)], x="segment", y=["customers", "at_risk"]
    )

    st.subheader("Call first: at-risk customers by contract value")
    table = pd.DataFrame([c.model_dump() for c in priority])
    st.dataframe(table[table["segment"].isin(selected)], hide_index=True)

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
