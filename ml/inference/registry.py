"""Locate and load the most recent trained churn model from MLflow."""

from pathlib import Path

from mlflow.tracking import MlflowClient

from ml.training.model import ChurnModel
from ml.training.train import load_model, tracking_uri_for


def load_latest_model(tracking_dir: Path, experiment: str) -> ChurnModel:
    if not (tracking_dir / "mlflow.db").exists():
        raise LookupError(f"no runs: tracking store not found in {tracking_dir}")
    client = MlflowClient(tracking_uri=tracking_uri_for(tracking_dir))
    found = client.get_experiment_by_name(experiment)
    runs = (
        client.search_runs(
            [found.experiment_id], order_by=["attributes.start_time DESC"], max_results=1
        )
        if found
        else []
    )
    if not runs:
        raise LookupError(f"no runs found in experiment '{experiment}'")
    return load_model(runs[0].info.run_id, tracking_dir)
