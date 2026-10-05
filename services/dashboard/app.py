"""Streamlit dashboard. Run with: make dashboard (needs the API: make api)."""

import altair as alt
import pandas as pd
import streamlit as st

from services.api.schemas import PortfolioSummaryOut, PriorityCustomerOut, PriorityListOut, Segment
from services.dashboard.client import ApiClient, ApiUnavailableError
from services.dashboard.metrics import (
    NO_SIGNAL,
    PRIORITY_COLUMNS,
    SEGMENT_ORDER,
    format_money,
    format_usage_change,
    kpis_for,
    loss_by_segment,
    priority_table,
    segment_frame,
    top_share,
)

TOP_N = 20


@st.cache_data(ttl=60)
def load_summary() -> PortfolioSummaryOut:
    return ApiClient.from_env().summary()


@st.cache_data(ttl=60)
def load_priority(segments: tuple[Segment, ...]) -> PriorityListOut | None:
    return ApiClient.from_env().priority(segments, limit=TOP_N)


def loss_chart(frame: pd.DataFrame) -> alt.LayerChart:
    """Horizontal bars with the value printed on each bar."""
    base = alt.Chart(frame).encode(
        y=alt.Y("segment:N", sort=SEGMENT_ORDER, title=None, axis=alt.Axis(labelFontSize=14)),
        x=alt.X(
            "expected_loss:Q", title="Expected loss per year (€)", axis=alt.Axis(format=",.0f")
        ),
    )
    bars = base.mark_bar(size=36)
    labels = base.mark_text(align="left", dx=6, fontSize=14).encode(
        text=alt.Text("expected_loss:Q", format=",.0f")
    )
    chart: alt.LayerChart = (bars + labels).properties(height=60 * max(len(frame), 1) + 40)
    return chart


def show_customer(customer: PriorityCustomerOut) -> None:
    st.subheader(f"Customer {customer.customer_id}")
    st.metric("Chance of leaving", f"{customer.churn_probability:.0%}")
    st.metric("Expected loss", format_money(customer.expected_loss))
    st.metric("Annual contract", format_money(customer.annual_contract_value))
    st.markdown("**Why this customer is flagged**")
    for signal in customer.signals or [NO_SIGNAL]:
        st.markdown(f"- {signal}")
    st.caption(
        f"{customer.segment} · {customer.industry} · {customer.employees:,} employees · "
        f"{customer.total_tickets} support tickets · usage "
        f"{format_usage_change(customer.usage_trend_ratio)} vs. the start of the period"
    )


def main() -> None:
    st.set_page_config(page_title="Customer 360: who to call first", layout="wide")
    st.title("Customer 360: who to call first")
    st.caption(
        "Synthetic B2B SaaS customers. A model estimates each customer's probability to churn; "
        "customers are ranked by expected loss = chance of leaving × annual contract. "
        "All amounts in euro."
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
        "- *Expected loss*: chance of leaving × annual contract, an estimate and not a promise.\n"
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

    if priority is None:
        st.warning(
            "The churn model is not loaded, so customers cannot be ranked. Run `make train`."
        )
        headline, active_customers, coverage = "n/a", kpis.customers, "n/a"
    else:
        headline = format_money(priority.total_expected_loss)
        active_customers = priority.customers_scored
        coverage = f"{top_share(priority.items, priority.total_expected_loss):.0%}"

    hero, *others = st.columns([2, 1, 1, 1])
    hero.metric(
        "Expected loss per year",
        headline,
        help=(
            "What the model expects to lose in a year: for every active customer, "
            "chance of leaving × annual contract. An estimate, not a promise."
        ),
    )
    others[0].metric("Active customers", f"{active_customers:,}")
    others[1].metric(
        "With a usage drop",
        f"{kpis.at_risk:,}",
        delta=f"{kpis.at_risk_share:.1%} of customers",
        delta_color="off",
        help="Usage in the last 30 days fell more than 15% below the first 30 days.",
    )
    others[2].metric(
        f"Top {TOP_N} cover",
        coverage,
        help="Share of the total expected loss held by the customers in the list below.",
    )

    st.header("Who to call first")
    if priority is not None and not priority.items:
        st.info("No active customers in the selected segments.")
    elif priority is not None:
        st.caption(
            f"Top {len(priority.items)} of {priority.customers_scored:,} active customers by "
            "expected loss."
        )
        table_col, detail_col = st.columns([2, 1])
        with table_col:
            event = st.dataframe(
                priority_table(priority.items),
                hide_index=True,
                width="stretch",
                on_select="rerun",
                selection_mode="single-row",
                column_config={
                    PRIORITY_COLUMNS["contract"]: st.column_config.NumberColumn(format="localized"),
                    PRIORITY_COLUMNS["probability"]: st.column_config.ProgressColumn(
                        min_value=0.0, max_value=1.0, format="percent"
                    ),
                    PRIORITY_COLUMNS["loss"]: st.column_config.NumberColumn(format="localized"),
                    PRIORITY_COLUMNS["why"]: st.column_config.TextColumn(width="large"),
                },
            )
        with detail_col:
            rows = event.selection.rows
            if rows:
                show_customer(priority.items[rows[0]])
            else:
                st.info("Click a row in the table to see why this customer is flagged.")

    if priority is not None:
        st.header("Where the expected loss is")
        st.caption(
            "Expected loss per year by segment, all active customers (not only the top list)."
        )
        st.altair_chart(loss_chart(loss_by_segment(priority.by_segment, selected)))


main()
