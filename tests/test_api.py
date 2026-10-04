from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from ml.inference.registry import load_latest_model
from ml.training.model import ChurnModel
from ml.training.train import load_features, predict_proba, train_and_log
from services.api.main import create_app
from services.api.predictor import ChurnPredictor
from services.api.repository import CustomerRepository
from tests.dbt_helpers import build_warehouse

SEED = 11
EXPERIMENT = "api-test"
CUSTOMER_FIELDS = {
    "customer_id",
    "segment",
    "employees",
    "industry",
    "contract_end_date",
    "annual_contract_value",
    "avg_daily_usage",
    "usage_trend_ratio",
    "total_tickets",
    "is_at_risk",
    "is_churned",
}


@pytest.fixture(scope="module")
def env(tmp_path_factory: pytest.TempPathFactory) -> tuple[Path, Path]:
    work = tmp_path_factory.mktemp("api")
    db_path, _ = build_warehouse(work, 600, 60, seed=SEED)
    tracking_dir = work / "mlruns"
    train_and_log(load_features(db_path), tracking_dir, EXPERIMENT, SEED)
    return db_path, tracking_dir


@pytest.fixture(scope="module")
def model(env: tuple[Path, Path]) -> ChurnModel:
    return load_latest_model(env[1], EXPERIMENT)


@pytest.fixture(scope="module")
def client(env: tuple[Path, Path], model: ChurnModel) -> Iterator[TestClient]:
    app = create_app(CustomerRepository(env[0]), ChurnPredictor(model))
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture(scope="module")
def client_without_model(env: tuple[Path, Path]) -> Iterator[TestClient]:
    with TestClient(create_app(CustomerRepository(env[0]), None)) as test_client:
        yield test_client


def test_latest_model_loader_returns_a_usable_model(
    env: tuple[Path, Path], model: ChurnModel
) -> None:
    probabilities = predict_proba(model, load_features(env[0]).head(3))
    assert len(probabilities) == 3


def test_load_latest_model_fails_clearly_when_no_runs_exist(tmp_path: Path) -> None:
    with pytest.raises(LookupError, match="no runs"):
        load_latest_model(tmp_path / "empty", EXPERIMENT)


def test_health_reports_model_loaded(client: TestClient) -> None:
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "model_loaded": True}


def test_health_reports_missing_model(client_without_model: TestClient) -> None:
    assert client_without_model.get("/health").json() == {"status": "ok", "model_loaded": False}


def test_get_customer_returns_the_contract_fields(client: TestClient) -> None:
    response = client.get("/customers/C000000")
    assert response.status_code == 200
    assert set(response.json()) == CUSTOMER_FIELDS
    assert response.json()["customer_id"] == "C000000"


def test_unknown_customer_returns_404(client: TestClient) -> None:
    response = client.get("/customers/DOES-NOT-EXIST")
    assert response.status_code == 404
    assert "DOES-NOT-EXIST" in response.json()["detail"]


def test_list_filters_by_segment(client: TestClient) -> None:
    rows = client.get("/customers", params={"segment": "ENTERPRISE", "limit": 100}).json()
    assert rows
    assert {row["segment"] for row in rows} == {"ENTERPRISE"}


def test_list_filters_by_at_risk(client: TestClient) -> None:
    at_risk = client.get("/customers", params={"at_risk": "true", "limit": 100}).json()
    not_at_risk = client.get("/customers", params={"at_risk": "false", "limit": 100}).json()
    assert at_risk
    assert all(row["is_at_risk"] for row in at_risk)
    assert not any(row["is_at_risk"] for row in not_at_risk)


def test_list_respects_limit(client: TestClient) -> None:
    assert len(client.get("/customers", params={"limit": 5}).json()) == 5


@pytest.mark.parametrize(
    "params",
    [{"segment": "NOT_A_SEGMENT"}, {"limit": 0}, {"limit": 1001}],
)
def test_invalid_list_parameters_return_422(client: TestClient, params: dict[str, object]) -> None:
    assert client.get("/customers", params=params).status_code == 422


def test_predict_matches_the_model_for_the_same_customer(
    client: TestClient, env: tuple[Path, Path], model: ChurnModel
) -> None:
    features = load_features(env[0])
    row = features[features["customer_id"] == "C000001"]
    expected = float(predict_proba(model, row)[0])
    response = client.post("/predict/churn", json={"customer_id": "C000001"})
    assert response.status_code == 200
    body = response.json()
    assert body["customer_id"] == "C000001"
    assert 0.0 <= body["churn_probability"] <= 1.0
    assert body["churn_probability"] == pytest.approx(expected)


def test_predict_for_unknown_customer_returns_404(client: TestClient) -> None:
    response = client.post("/predict/churn", json={"customer_id": "DOES-NOT-EXIST"})
    assert response.status_code == 404


def test_predict_without_model_returns_503(client_without_model: TestClient) -> None:
    response = client_without_model.post("/predict/churn", json={"customer_id": "C000001"})
    assert response.status_code == 503


def test_predict_rejects_missing_customer_id(client: TestClient) -> None:
    assert client.post("/predict/churn", json={}).status_code == 422
