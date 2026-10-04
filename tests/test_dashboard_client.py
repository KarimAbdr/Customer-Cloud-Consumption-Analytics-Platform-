from collections.abc import Iterator
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient

from services.api.main import create_app
from services.api.repository import CustomerRepository
from services.dashboard.client import ApiClient, ApiUnavailableError
from tests.dbt_helpers import build_warehouse


@pytest.fixture(scope="module")
def client(tmp_path_factory: pytest.TempPathFactory) -> Iterator[ApiClient]:
    """The real API (no model) over a small real warehouse: guards against contract drift."""
    db_path, _ = build_warehouse(tmp_path_factory.mktemp("dash"), 300, 40, seed=5)
    with TestClient(create_app(CustomerRepository(db_path), None)) as http:
        yield ApiClient(http)


def test_customers_are_parsed_into_typed_models(client: ApiClient) -> None:
    customers = client.customers(limit=20)
    assert len(customers) == 20
    assert customers[0].customer_id.startswith("C")


def test_customers_filter_by_segment(client: ApiClient) -> None:
    assert {c.segment for c in client.customers(segment="SMB", limit=50)} == {"SMB"}


def test_customer_returns_none_for_unknown_id(client: ApiClient) -> None:
    assert client.customer("NOPE") is None


def test_customer_returns_profile_for_known_id(client: ApiClient) -> None:
    known = client.customers(limit=1)[0]
    assert client.customer(known.customer_id) == known


def test_predict_is_none_when_model_is_not_loaded(client: ApiClient) -> None:
    known = client.customers(limit=1)[0]
    assert client.predict(known.customer_id) is None


def test_summary_is_parsed_and_covers_the_whole_portfolio(client: ApiClient) -> None:
    summary = client.summary()
    assert summary.customers == 300
    assert sum(s.customers for s in summary.segments) == 300


def test_customers_can_be_ordered_by_value(client: ApiClient) -> None:
    values = [c.annual_contract_value for c in client.customers(order="value", limit=30)]
    assert values == sorted(values, reverse=True)


def test_health_reports_model_state(client: ApiClient) -> None:
    assert client.health().model_loaded is False


def test_unreachable_api_raises_a_clear_error() -> None:
    def refuse(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused", request=request)

    api = ApiClient(httpx.Client(base_url="http://x", transport=httpx.MockTransport(refuse)))
    with pytest.raises(ApiUnavailableError, match="unreachable"):
        api.health()


def test_server_error_raises_a_clear_error() -> None:
    api = ApiClient(
        httpx.Client(
            base_url="http://x", transport=httpx.MockTransport(lambda r: httpx.Response(500))
        )
    )
    with pytest.raises(ApiUnavailableError, match="500"):
        api.customers()


def test_predict_returns_probability_from_response() -> None:
    api = ApiClient(
        httpx.Client(
            base_url="http://x",
            transport=httpx.MockTransport(
                lambda r: httpx.Response(200, json={"customer_id": "C1", "churn_probability": 0.3})
            ),
        )
    )
    assert api.predict("C1") == 0.3


def test_default_client_points_at_env_url(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("API_URL", "http://example.test:1234")
    assert str(ApiClient.from_env()._http.base_url).startswith("http://example.test:1234")
