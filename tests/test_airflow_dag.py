from pathlib import Path

import pytest
from airflow.dag_processing.dagbag import DagBag
from airflow.providers.standard.operators.bash import BashOperator
from airflow.sdk import DAG
from airflow.sdk.definitions.timetables.trigger import CronTriggerTimetable

DAGS_DIR = Path(__file__).resolve().parent.parent / "dags"
DAG_ID = "customer360_pipeline"


@pytest.fixture(scope="module")
def dag_bag() -> DagBag:
    return DagBag(dag_folder=str(DAGS_DIR), include_examples=False)


@pytest.fixture(scope="module")
def dag(dag_bag: DagBag) -> DAG:
    return dag_bag.dags[DAG_ID]


def test_dag_files_import_without_errors(dag_bag: DagBag) -> None:
    assert dag_bag.import_errors == {}


def test_dag_is_registered(dag_bag: DagBag) -> None:
    assert DAG_ID in dag_bag.dags


def test_dag_has_the_three_pipeline_tasks(dag: DAG) -> None:
    assert set(dag.task_ids) == {"ingest", "dbt_build", "train_model"}


def test_tasks_run_in_pipeline_order(dag: DAG) -> None:
    assert dag.get_task("ingest").downstream_task_ids == {"dbt_build"}
    assert dag.get_task("dbt_build").downstream_task_ids == {"train_model"}
    assert dag.get_task("train_model").downstream_task_ids == set()


@pytest.mark.parametrize(
    ("task_id", "make_target"),
    [("ingest", "ingest"), ("dbt_build", "dbt"), ("train_model", "train")],
)
def test_each_task_only_calls_its_make_target(dag: DAG, task_id: str, make_target: str) -> None:
    task = dag.get_task(task_id)
    assert isinstance(task, BashOperator)
    assert str(task.bash_command).strip() == f"make {make_target}"


def test_make_targets_used_by_the_dag_exist_in_the_makefile(dag: DAG) -> None:
    makefile = (DAGS_DIR.parent / "Makefile").read_text()
    for task in dag.tasks:
        assert isinstance(task, BashOperator)
        target = str(task.bash_command).split()[1]
        assert f"\n{target}:" in f"\n{makefile}"


def test_tasks_run_from_the_repository_root(dag: DAG) -> None:
    root = str(DAGS_DIR.parent)
    for task in dag.tasks:
        assert isinstance(task, BashOperator)
        assert task.cwd == root


def test_failed_tasks_are_retried_with_a_delay(dag: DAG) -> None:
    for task in dag.tasks:
        assert task.retries is not None
        assert task.retries >= 1
        assert task.retry_delay.total_seconds() > 0


def test_dag_is_daily_and_does_not_backfill(dag: DAG) -> None:
    timetable = dag.timetable
    assert isinstance(timetable, CronTriggerTimetable)
    assert timetable.expression == "@daily"
    assert dag.catchup is False
