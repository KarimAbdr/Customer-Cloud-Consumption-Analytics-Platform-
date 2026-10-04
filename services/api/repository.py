"""Read-only access to the gold layer in DuckDB."""

from pathlib import Path
from typing import Any

import duckdb
import pandas as pd


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
        self, segment: str | None, at_risk: bool | None, limit: int
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
            f"select * from customer_360 {where} order by customer_id limit ?", [*params, limit]
        )

    def get_features(self, customer_id: str) -> pd.DataFrame:
        """ML features of one customer; empty frame when the customer is unknown."""
        with duckdb.connect(self._db_path, read_only=True) as con:
            return con.execute(
                "select * from customer_features where customer_id = ?", [customer_id]
            ).df()
