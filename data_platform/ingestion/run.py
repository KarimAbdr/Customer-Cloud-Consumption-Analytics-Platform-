"""Bronze ingestion entry point: generate, validate, write Parquet.

Usable as a CLI (`python -m data_platform.ingestion.run`) and as a library, so an
orchestrator such as Airflow can stay a thin wrapper around `run_ingestion`.
"""

import argparse
from collections.abc import Sequence
from datetime import date
from pathlib import Path

import pandas as pd

from data_platform.ingestion.synthetic import (
    generate_churn_labels,
    generate_contracts,
    generate_customers,
    generate_dissatisfaction,
    generate_tickets,
    generate_usage,
)
from data_platform.quality.schemas import BRONZE_SCHEMAS

DEFAULT_START = date(2025, 1, 6)


def build_tables(n_customers: int, days: int, seed: int, start: date) -> dict[str, pd.DataFrame]:
    customers = generate_customers(n_customers, seed)
    contracts = generate_contracts(customers, seed)
    dissatisfaction = generate_dissatisfaction(n_customers, seed)
    months = max(1, days // 30)
    return {
        "customers": customers,
        "contracts": contracts,
        "daily_usage": generate_usage(
            customers, start, days, seed, dissatisfaction=dissatisfaction
        ),
        "support_tickets": generate_tickets(customers, start, months, seed, dissatisfaction),
        "churn_labels": generate_churn_labels(customers, contracts, dissatisfaction, seed),
    }


def write_bronze(tables: dict[str, pd.DataFrame], output_dir: Path) -> dict[str, int]:
    """Validate every table first, then write atomically (temp file + rename)."""
    for name, frame in tables.items():
        BRONZE_SCHEMAS[name].validate(frame)

    output_dir.mkdir(parents=True, exist_ok=True)
    for name, frame in tables.items():
        tmp = output_dir / f"{name}.parquet.tmp"
        frame.to_parquet(tmp, index=False)
        tmp.replace(output_dir / f"{name}.parquet")
    return {name: len(frame) for name, frame in tables.items()}


def run_ingestion(
    output_dir: Path, n_customers: int, days: int, seed: int, start: date = DEFAULT_START
) -> dict[str, int]:
    return write_bronze(build_tables(n_customers, days, seed, start), output_dir)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Generate bronze Parquet files.")
    parser.add_argument("--output-dir", type=Path, default=Path("data/bronze"))
    parser.add_argument("--customers", type=int, default=5_000)
    parser.add_argument("--days", type=int, default=180)
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args(argv)

    counts = run_ingestion(args.output_dir, args.customers, args.days, args.seed)
    for name, rows in counts.items():
        print(f"{name}: {rows} rows")
    print(f"Written to {args.output_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
