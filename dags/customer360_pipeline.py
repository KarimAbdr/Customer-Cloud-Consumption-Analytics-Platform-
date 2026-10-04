"""Daily Customer 360 pipeline.

A thin wrapper: every task only calls the same `make` target a person (or CI) would run, so the
pipeline is defined once, in the Makefile, and works without Airflow (`make pipeline`).
"""

from datetime import datetime, timedelta
from pathlib import Path

from airflow.providers.standard.operators.bash import BashOperator
from airflow.sdk import DAG

REPO_ROOT = str(Path(__file__).resolve().parent.parent)

with DAG(
    dag_id="customer360_pipeline",
    description="ingest -> dbt build -> train churn model",
    schedule="@daily",
    start_date=datetime(2025, 1, 1),
    catchup=False,
    default_args={"retries": 2, "retry_delay": timedelta(minutes=5)},
    tags=["customer360"],
):

    def make(task_id: str, target: str) -> BashOperator:
        return BashOperator(task_id=task_id, bash_command=f"make {target}", cwd=REPO_ROOT)

    ingest = make("ingest", "ingest")
    dbt_build = make("dbt_build", "dbt")
    train_model = make("train_model", "train")

    ingest >> dbt_build >> train_model
