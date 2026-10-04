"""Read-only access to the gold layer in DuckDB."""

from collections.abc import Sequence
from pathlib import Path
from typing import Any, Literal

import duckdb
import pandas as pd

CustomerOrder = Literal["id", "value"]
_ORDER_SQL: dict[CustomerOrder, str] = {
    "id": "customer_id",
    "value": "annual_contract_value desc, customer_id",
}


class CustomerRepository:
    def __init__(self, db_path: Path) -> None:
        self._db_path = str(db_path)

    def _rows(self, sql: str, params: list[Any]) -> list[dict[str, Any]]:
        with duckdb.connect(self._db_path, read_only=True) as con:
            cursor = con.execute(sql, params)
            columns = [d[0] for d in cursor.description]
            return [dict(zip(columns, row, strict=True)) for row in cursor.fetchall()]

    def get_customer(self, customer_id: str) -> dict[str, Any] | None:
        rows = self._rows("select * from customer_360 where customer_id = ?", [customer_id])
        return rows[0] if rows else None

    def list_customers(
        self,
        segment: str | None,
        at_risk: bool | None,
        limit: int,
        order: CustomerOrder = "id",
    ) -> list[dict[str, Any]]:
        conditions: list[str] = []
        params: list[Any] = []
        if segment is not None:
            conditions.append("segment = ?")
            params.append(segment)
        if at_risk is not None:
            conditions.append("is_at_risk = ?")
            params.append(at_risk)
        where = f"where {' and '.join(conditions)}" if conditions else ""
        return self._rows(
            f"select * from customer_360 {where} order by {_ORDER_SQL[order]} limit ?",
            [*params, limit],
        )

    def portfolio_summary(self) -> dict[str, Any]:
        """Aggregates over the whole portfolio, computed in SQL (no row limit)."""
        segments = self._rows(
            """
            select
                segment,
                count(*) as customers,
                count(*) filter (where is_at_risk) as at_risk,
                coalesce(sum(annual_contract_value) filter (where is_at_risk), 0)
                    as annual_revenue_at_risk
            from customer_360
            group by segment
            order by segment
            """,
            [],
        )
        customers = sum(s["customers"] for s in segments)
        at_risk = sum(s["at_risk"] for s in segments)
        return {
            "customers": customers,
            "at_risk": at_risk,
            "at_risk_share": at_risk / customers if customers else 0.0,
            "annual_revenue_at_risk": float(sum(s["annual_revenue_at_risk"] for s in segments)),
            "segments": segments,
        }

    def get_features(self, customer_id: str) -> pd.DataFrame:
        """ML features of one customer; empty frame when the customer is unknown."""
        with duckdb.connect(self._db_path, read_only=True) as con:
            return con.execute(
                "select * from customer_features where customer_id = ?", [customer_id]
            ).df()

    def active_customers(self, segments: Sequence[str] | None) -> pd.DataFrame:
        """Feature rows of customers that have not churned yet, optionally within segments."""
        where = "not cast(is_churned as boolean)"
        params: list[Any] = []
        if segments:
            where += f" and segment in ({', '.join('?' for _ in segments)})"
            params = list(segments)
        with duckdb.connect(self._db_path, read_only=True) as con:
            return con.execute(
                f"select * from customer_features where {where} order by customer_id", params
            ).df()
