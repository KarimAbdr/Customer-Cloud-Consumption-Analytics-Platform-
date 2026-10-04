"""Thin HTTP client for the Customer 360 API. The dashboard talks to nothing else."""

import os
from collections.abc import Sequence

import httpx

from services.api.repository import CustomerOrder
from services.api.schemas import (
    ChurnPredictionOut,
    CustomerOut,
    HealthOut,
    PortfolioSummaryOut,
    PriorityListOut,
    Segment,
)

DEFAULT_API_URL = "http://localhost:8010"


class ApiUnavailableError(RuntimeError):
    """The API is unreachable or answered with an unexpected error."""


class ApiClient:
    def __init__(self, http: httpx.Client) -> None:
        self._http = http

    @classmethod
    def from_env(cls) -> "ApiClient":
        return cls(httpx.Client(base_url=os.environ.get("API_URL", DEFAULT_API_URL), timeout=10))

    def _get(self, path: str, params: dict[str, object] | None = None) -> httpx.Response:
        try:
            response = self._http.get(path, params=params)  # type: ignore[arg-type]
        except httpx.TransportError as error:
            raise ApiUnavailableError(f"API unreachable: {error}") from error
        return self._checked(response)

    @staticmethod
    def _checked(response: httpx.Response) -> httpx.Response:
        if response.status_code >= 500 and response.status_code != 503:
            raise ApiUnavailableError(f"API error {response.status_code}")
        return response

    def health(self) -> HealthOut:
        return HealthOut.model_validate(self._get("/health").json())

    def customers(
        self,
        segment: Segment | None = None,
        at_risk: bool | None = None,
        limit: int = 50,
        order: CustomerOrder = "id",
    ) -> list[CustomerOut]:
        params: dict[str, object] = {"limit": limit, "order": order}
        if segment is not None:
            params["segment"] = segment
        if at_risk is not None:
            params["at_risk"] = at_risk
        response = self._get("/customers", params)
        if response.status_code != 200:
            raise ApiUnavailableError(f"API error {response.status_code}")
        return [CustomerOut.model_validate(item) for item in response.json()]

    def summary(self) -> PortfolioSummaryOut:
        response = self._get("/portfolio/summary")
        if response.status_code != 200:
            raise ApiUnavailableError(f"API error {response.status_code}")
        return PortfolioSummaryOut.model_validate(response.json())

    def priority(
        self, segments: Sequence[Segment] | None, limit: int = 20
    ) -> PriorityListOut | None:
        """Customers ranked by expected loss; None when the churn model is not loaded."""
        params: list[tuple[str, str | int | float | bool | None]] = [("limit", limit)]
        params += [("segment", name) for name in segments or []]
        try:
            response = self._http.get("/portfolio/priority", params=params)
        except httpx.TransportError as error:
            raise ApiUnavailableError(f"API unreachable: {error}") from error
        if response.status_code == 503:
            return None
        if response.status_code != 200:
            raise ApiUnavailableError(f"API error {response.status_code}")
        return PriorityListOut.model_validate(response.json())

    def customer(self, customer_id: str) -> CustomerOut | None:
        response = self._get(f"/customers/{customer_id}")
        if response.status_code == 404:
            return None
        if response.status_code != 200:
            raise ApiUnavailableError(f"API error {response.status_code}")
        return CustomerOut.model_validate(response.json())

    def predict(self, customer_id: str) -> float | None:
        """Churn probability, or None when the model is not loaded or the customer is unknown."""
        try:
            response = self._http.post("/predict/churn", json={"customer_id": customer_id})
        except httpx.TransportError as error:
            raise ApiUnavailableError(f"API unreachable: {error}") from error
        if response.status_code in (404, 503):
            return None
        self._checked(response)
        if response.status_code != 200:
            raise ApiUnavailableError(f"API error {response.status_code}")
        return ChurnPredictionOut.model_validate(response.json()).churn_probability
