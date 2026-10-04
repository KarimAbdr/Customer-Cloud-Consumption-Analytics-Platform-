"""Churn model training: LightGBM classifier tracked with MLflow.

`train_model` is a pure function of the feature table and a seed, so it can be
tested without a database or an MLflow server.
"""

import argparse
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import duckdb
import mlflow
import mlflow.sklearn
import numpy as np
import pandas as pd
from lightgbm import LGBMClassifier
from sklearn.metrics import average_precision_score, roc_auc_score
from sklearn.model_selection import train_test_split

from ml.training.model import ChurnModel

ID_COLUMN = "customer_id"
TARGET_COLUMN = "is_churned"
CATEGORICAL_COLUMNS = ("segment", "industry")
MODEL_ARTIFACT = "churn_model"


@dataclass(frozen=True)
class TrainResult:
    model: ChurnModel
    metrics: dict[str, float]


def load_features(db_path: Path) -> pd.DataFrame:
    with duckdb.connect(str(db_path), read_only=True) as con:
        return con.execute("select * from customer_features order by customer_id").df()


def select_feature_columns(features: pd.DataFrame) -> list[str]:
    return [c for c in features.columns if c not in (ID_COLUMN, TARGET_COLUMN)]


def _prepare(
    features: pd.DataFrame, feature_names: list[str], categories: dict[str, list[str]]
) -> pd.DataFrame:
    frame = features[feature_names].copy()
    for column, levels in categories.items():
        # Levels unseen in training become missing instead of raising.
        known = frame[column].where(frame[column].isin(levels))
        frame[column] = pd.Categorical(known, categories=levels)
    return frame


def train_model(
    features: pd.DataFrame, seed: int, params: dict[str, Any] | None = None
) -> TrainResult:
    feature_names = select_feature_columns(features)
    categories = {c: sorted(features[c].dropna().unique()) for c in CATEGORICAL_COLUMNS}
    x = _prepare(features, feature_names, categories)
    y = features[TARGET_COLUMN].astype(int)
    x_train, x_test, y_train, y_test = train_test_split(
        x, y, test_size=0.25, stratify=y, random_state=seed
    )

    estimator = LGBMClassifier(
        **{
            "n_estimators": 200,
            "learning_rate": 0.05,
            "num_leaves": 15,
            "min_child_samples": 20,
            # Churn is the minority class; reweight instead of resampling.
            "scale_pos_weight": float((y_train == 0).sum() / max(1, (y_train == 1).sum())),
            "random_state": seed,
            "deterministic": True,
            "force_row_wise": True,
            "n_jobs": 1,
            "verbose": -1,
            **(params or {}),
        }
    )
    estimator.fit(x_train, y_train)

    probabilities = np.asarray(estimator.predict_proba(x_test))[:, 1]
    metrics = {
        "roc_auc": float(roc_auc_score(y_test, probabilities)),
        "pr_auc": float(average_precision_score(y_test, probabilities)),
    }
    return TrainResult(ChurnModel(estimator, feature_names, categories), metrics)


def predict_proba(model: ChurnModel, features: pd.DataFrame) -> np.ndarray:
    prepared = _prepare(features, model.feature_names, model.categories)
    return np.asarray(model.estimator.predict_proba(prepared))[:, 1]


def tracking_uri_for(tracking_dir: Path) -> str:
    """MLflow 3 deprecates the plain file store; use SQLite metadata + local artifacts."""
    return f"sqlite:///{(tracking_dir / 'mlflow.db').resolve()}"


def _configure_mlflow(tracking_dir: Path, experiment: str | None = None) -> None:
    tracking_dir.mkdir(parents=True, exist_ok=True)
    mlflow.set_tracking_uri(tracking_uri_for(tracking_dir))
    if experiment is None:
        return
    if mlflow.get_experiment_by_name(experiment) is None:
        mlflow.create_experiment(
            experiment, artifact_location=(tracking_dir / "artifacts").resolve().as_uri()
        )
    mlflow.set_experiment(experiment)


def train_and_log(features: pd.DataFrame, tracking_dir: Path, experiment: str, seed: int) -> str:
    _configure_mlflow(tracking_dir, experiment)
    result = train_model(features, seed=seed)
    with mlflow.start_run() as run:
        mlflow.log_params(
            {"seed": seed, "n_rows": len(features), **result.model.estimator.get_params()}
        )
        mlflow.log_metrics(result.metrics)
        # cloudpickle: the default skops format rejects our wrapper type. Only load
        # models from a tracking store we control.
        mlflow.sklearn.log_model(
            result.model, artifact_path=MODEL_ARTIFACT, serialization_format="cloudpickle"
        )
        return str(run.info.run_id)


def load_model(run_id: str, tracking_dir: Path) -> ChurnModel:
    _configure_mlflow(tracking_dir)
    model = mlflow.sklearn.load_model(f"runs:/{run_id}/{MODEL_ARTIFACT}")
    assert isinstance(model, ChurnModel)
    return model


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Train the churn model.")
    parser.add_argument("--db-path", type=Path, default=Path("data/warehouse.duckdb"))
    parser.add_argument("--tracking-dir", type=Path, default=Path("mlruns"))
    parser.add_argument("--experiment", default="churn")
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args(argv)

    run_id = train_and_log(
        load_features(args.db_path), args.tracking_dir, args.experiment, args.seed
    )
    metrics = mlflow.get_run(run_id).data.metrics
    print(f"run_id: {run_id}")
    for name in ("roc_auc", "pr_auc"):
        print(f"{name}: {metrics[name]:.3f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
