"""Streamlit dashboard. Run with: make dashboard (needs the API: make api)."""

import streamlit as st

from services.api.schemas import PortfolioSummaryOut, PriorityCustomerOut, PriorityListOut, Segment
from services.dashboard.client import ApiClient, ApiUnavailableError
from services.dashboard.metrics import (
    NO_SIGNAL,
    SEGMENT_ORDER,
    kpis_for,
    priority_table,
    segment_frame,
)

TOP_N = 20


@st.cache_data(ttl=60)
def load_summary() -> PortfolioSummaryOut:
    return ApiClient.from_env().summary()


@st.cache_data(ttl=60)
def load_priority(segments: tuple[Segment, ...]) -> PriorityListOut | None:
    return ApiClient.from_env().priority(segments, limit=TOP_N)


def show_customer(customer: PriorityCustomerOut) -> None:
    st.subheader(f"Customer {customer.customer_id}")
    left, right = st.columns([1, 2])
    with left:
        st.metric("Churn probability", f"{customer.churn_probability:.0%}")
        st.metric("Expected loss", f"{customer.expected_loss:,.0f}")
        st.metric("Contract / year", f"{customer.annual_contract_value:,.0f}")
    with right:
        st.markdown("**Why this customer is flagged**")
        if customer.signals:
            for signal in customer.signals:
                st.markdown(f"- {signal}")
        else:
            st.markdown(f"- {NO_SIGNAL}")
        st.caption(
            f"{customer.segment} · {customer.industry} · {customer.employees:,} employees · "
            f"{customer.total_tickets} support tickets · usage trend "
            f"{customer.usage_trend_ratio:.2f}x (last 30 days vs first 30)"
        )


def main() -> None:
    st.set_page_config(page_title="Customer 360: who to call first", layout="wide")
    st.title("Customer 360: who to call first")
    st.caption(
        "Synthetic B2B SaaS customers. A model estimates each customer's probability to churn; "
        "customers are ranked by expected loss = churn probability × annual contract value."
    )

    try:
        summary = load_summary()
    except ApiUnavailableError as error:
        st.error(f"{error}. Start the API with `make api`.")
        return
    if summary.customers == 0:
        st.warning("The portfolio is empty. Run `make pipeline` first.")
        return

    selected = st.sidebar.multiselect("Segments", SEGMENT_ORDER, default=SEGMENT_ORDER)
    st.sidebar.markdown(
        "**How to read this**\n\n"
        "- *Usage drop*: usage in the last 30 days is more than 15% below the first 30 days.\n"
        "- *Expected loss*: what the model expects to lose from a customer, "
        "not a promise.\n"
        "- Already churned customers are never listed."
    )
    if not selected:
        st.info("Select at least one segment in the sidebar.")
        return

    segments = segment_frame(summary)
    kpis = kpis_for(segments, selected)
    try:
        priority = load_priority(tuple(selected))
    except ApiUnavailableError as error:
        st.error(f"{error}. Start the API with `make api`.")
        return

    columns = st.columns(4)
    columns[0].metric(
        "Customers", f"{kpis.customers:,}", help="Customers in the selected segments."
    )
    columns[1].metric(
        "With a usage drop",
        f"{kpis.at_risk:,}",
        delta=f"{kpis.at_risk_share:.1%} of customers",
        delta_color="off",
        help="Usage in the last 30 days fell more than 15% below the first 30 days.",
    )
    columns[2].metric(
        "Contract value with a usage drop",
        f"{kpis.annual_revenue_at_risk:,.0f}",
        help="Annual contract value of the customers with a usage drop.",
    )
    if priority is None:
        columns[3].metric("Expected loss (model)", "n/a")
    else:
        columns[3].metric(
            "Expected loss (model)",
            f"{priority.total_expected_loss:,.0f}",
            help="Sum over all active customers of churn probability × annual contract value.",
        )

    st.header("Who to call first")
    if priority is None:
        st.warning(
            "The churn model is not loaded, so customers cannot be ranked. Run `make train`."
        )
    elif not priority.items:
        st.info("No active customers in the selected segments.")
    else:
        st.caption(
            f"Top {len(priority.items)} of {priority.customers_scored:,} active customers by "
            "expected loss. Click a row to see why."
        )
        event = st.dataframe(
            priority_table(priority.items),
            hide_index=True,
            width="stretch",
            on_select="rerun",
            selection_mode="single-row",
            column_config={
                "Contract / year": st.column_config.NumberColumn(format="localized"),
                "Churn probability": st.column_config.ProgressColumn(
                    min_value=0.0, max_value=1.0, format="percent"
                ),
                "Expected loss": st.column_config.NumberColumn(format="localized"),
                "Why": st.column_config.TextColumn(width="large"),
            },
        )
        rows = event.selection.rows
        show_customer(priority.items[rows[0] if rows else 0])

    st.header("Segments")
    left, right = st.columns(2)
    chosen = segments[segments["segment"].isin(selected)]
    with left:
        st.markdown("**Customers with a usage drop, % of the segment**")
        st.bar_chart(chosen, x="segment", y="at_risk_share", horizontal=True)
    with right:
        st.markdown("**Contract value with a usage drop**")
        st.bar_chart(chosen, x="segment", y="annual_revenue_at_risk", horizontal=True)


main()
