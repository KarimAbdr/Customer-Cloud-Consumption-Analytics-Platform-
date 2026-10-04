"""Pandera data contracts for the bronze layer."""

import pandera.pandas as pa

from data_platform.ingestion.synthetic import SEGMENTS

BRONZE_SCHEMAS: dict[str, pa.DataFrameSchema] = {
    "customers": pa.DataFrameSchema(
        {
            "customer_id": pa.Column(unique=True, nullable=False),
            "segment": pa.Column(checks=pa.Check.isin(SEGMENTS), nullable=False),
            "employees": pa.Column(int, checks=pa.Check.ge(1)),
            "industry": pa.Column(nullable=True),
        },
        strict=True,
    ),
    "contracts": pa.DataFrameSchema(
        {
            "customer_id": pa.Column(unique=True, nullable=False),
            "start_date": pa.Column("datetime64[ns]"),
            "end_date": pa.Column("datetime64[ns]"),
            "term_months": pa.Column(int, checks=pa.Check.isin([12, 24, 36])),
            "monthly_fee": pa.Column(float, checks=pa.Check.ge(0)),
        },
        strict=True,
    ),
    "daily_usage": pa.DataFrameSchema(
        {
            "customer_id": pa.Column(nullable=False),
            "usage_date": pa.Column("datetime64[ns]"),
            "daily_usage": pa.Column(float, checks=pa.Check.ge(0)),
        },
        unique=["customer_id", "usage_date"],
        strict=True,
    ),
    "support_tickets": pa.DataFrameSchema(
        {
            "customer_id": pa.Column(nullable=False),
            "month": pa.Column("datetime64[ns]"),
            "ticket_count": pa.Column(int, checks=pa.Check.ge(0)),
        },
        unique=["customer_id", "month"],
        strict=True,
    ),
    "churn_labels": pa.DataFrameSchema(
        {
            "customer_id": pa.Column(unique=True, nullable=False),
            "churned": pa.Column(int, checks=pa.Check.isin([0, 1])),
        },
        strict=True,
    ),
}
