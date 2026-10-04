from datetime import date
from pathlib import Path

import pandas as pd
import pytest
from pandera.errors import SchemaError

from data_platform.ingestion.run import build_tables, main, run_ingestion, write_bronze

TABLES = ("customers", "contracts", "daily_usage", "support_tickets", "churn_labels")
START = date(2025, 1, 6)


def test_run_creates_one_parquet_file_per_table(tmp_path: Path) -> None:
    run_ingestion(tmp_path, n_customers=50, days=14, seed=1, start=START)
    assert {p.name for p in tmp_path.glob("*.parquet")} == {f"{t}.parquet" for t in TABLES}


def test_run_returns_row_counts(tmp_path: Path) -> None:
    counts = run_ingestion(tmp_path, n_customers=50, days=14, seed=1, start=START)
    assert counts["customers"] == 50
    assert counts["daily_usage"] == 50 * 14


def test_written_data_reads_back_unchanged(tmp_path: Path) -> None:
    run_ingestion(tmp_path, n_customers=50, days=14, seed=1, start=START)
    expected = build_tables(n_customers=50, days=14, seed=1, start=START)
    for name in TABLES:
        actual = pd.read_parquet(tmp_path / f"{name}.parquet")
        pd.testing.assert_frame_equal(actual, expected[name], check_dtype=False)


def test_same_seed_produces_identical_output(tmp_path: Path) -> None:
    first, second = tmp_path / "a", tmp_path / "b"
    run_ingestion(first, n_customers=50, days=14, seed=3, start=START)
    run_ingestion(second, n_customers=50, days=14, seed=3, start=START)
    for name in TABLES:
        pd.testing.assert_frame_equal(
            pd.read_parquet(first / f"{name}.parquet"),
            pd.read_parquet(second / f"{name}.parquet"),
        )


def test_rerun_into_same_directory_overwrites_cleanly(tmp_path: Path) -> None:
    run_ingestion(tmp_path, n_customers=50, days=14, seed=1, start=START)
    run_ingestion(tmp_path, n_customers=20, days=7, seed=1, start=START)
    assert len(pd.read_parquet(tmp_path / "customers.parquet")) == 20
    assert not list(tmp_path.glob("*.tmp"))


def test_invalid_data_is_rejected_and_nothing_is_written(tmp_path: Path) -> None:
    tables = build_tables(n_customers=50, days=14, seed=1, start=START)
    tables["daily_usage"].loc[0, "daily_usage"] = -1.0
    with pytest.raises(SchemaError):
        write_bronze(tables, tmp_path)
    assert not list(tmp_path.iterdir())


def test_cli_returns_zero_and_prints_summary(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    code = main(["--output-dir", str(tmp_path), "--customers", "50", "--days", "14", "--seed", "1"])
    out = capsys.readouterr().out
    assert code == 0
    assert "customers" in out
    assert "50" in out
