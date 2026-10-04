from pathlib import Path

import numpy as np
import pandas as pd
import pytest
from mlflow.tracking import MlflowClient

from ml.training.train import (
    load_features,
    load_model,
    predict_proba,
    select_feature_columns,
    tracking_uri_for,
    train_and_log,
    train_model,
)
from tests.dbt_helpers import build_warehouse

SEED = 5


@pytest.fixture(scope="module")
def features(tmp_path_factory: pytest.TempPathFactory) -> pd.DataFrame:
    db_path, _ = build_warehouse(tmp_path_factory.mktemp("ml"), 2_000, 60, seed=SEED)
    return load_features(db_path)


def test_feature_columns_exclude_id_and_target(features: pd.DataFrame) -> None:
    columns = select_feature_columns(features)
    assert "customer_id" not in columns
    assert "is_churned" not in columns
    assert "usage_trend_ratio" in columns


def test_training_is_deterministic_for_same_seed(features: pd.DataFrame) -> None:
    first = train_model(features, seed=SEED)
    second = train_model(features, seed=SEED)
    np.testing.assert_array_equal(
        predict_proba(first.model, features), predict_proba(second.model, features)
    )


def test_holdout_roc_auc_beats_chance_but_is_not_suspiciously_perfect(
    features: pd.DataFrame,
) -> None:
    result = train_model(features, seed=SEED)
    assert 0.70 <= result.metrics["roc_auc"] <= 0.95
    assert 0.0 < result.metrics["pr_auc"] <= 1.0


def test_probabilities_are_in_unit_interval(features: pd.DataFrame) -> None:
    probabilities = predict_proba(train_model(features, seed=SEED).model, features)
    assert len(probabilities) == len(features)
    assert ((probabilities >= 0) & (probabilities <= 1)).all()


def test_unseen_category_does_not_break_prediction(features: pd.DataFrame) -> None:
    model = train_model(features, seed=SEED).model
    unseen = features.head(5).assign(industry="NEW_INDUSTRY", segment="NEW_SEGMENT")
    probabilities = predict_proba(model, unseen)
    assert ((probabilities >= 0) & (probabilities <= 1)).all()


def test_train_and_log_records_metrics_and_model(features: pd.DataFrame, tmp_path: Path) -> None:
    tracking_dir = tmp_path / "mlruns"
    run_id = train_and_log(features, tracking_dir=tracking_dir, experiment="test", seed=SEED)
    run = MlflowClient(tracking_uri=tracking_uri_for(tracking_dir)).get_run(run_id)
    assert {"roc_auc", "pr_auc"} <= set(run.data.metrics)
    assert run.data.params["seed"] == str(SEED)


def test_logged_model_gives_same_predictions_after_reload(
    features: pd.DataFrame, tmp_path: Path
) -> None:
    tracking_dir = tmp_path / "mlruns"
    run_id = train_and_log(features, tracking_dir=tracking_dir, experiment="test", seed=SEED)
    reloaded = load_model(run_id, tracking_dir=tracking_dir)
    original = train_model(features, seed=SEED).model
    np.testing.assert_allclose(
        predict_proba(reloaded, features), predict_proba(original, features), rtol=1e-9
    )
