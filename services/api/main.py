"""Customer 360 API. Run with: uvicorn services.api.main:create_app --factory"""

import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Annotated

from fastapi import Depends, FastAPI, HTTPException, Query, Request

from ml.inference.registry import load_latest_model
from services.api.predictor import ChurnPredictor
from services.api.repository import CustomerRepository
from services.api.schemas import (
    ChurnPredictionOut,
    CustomerOut,
    HealthOut,
    PredictRequest,
    Segment,
)


def get_repository(request: Request) -> CustomerRepository:
    repository: CustomerRepository = request.app.state.repository
    return repository


def get_predictor(request: Request) -> ChurnPredictor | None:
    predictor: ChurnPredictor | None = request.app.state.predictor
    return predictor


Repository = Annotated[CustomerRepository, Depends(get_repository)]
Predictor = Annotated[ChurnPredictor | None, Depends(get_predictor)]


def _load_default_predictor() -> ChurnPredictor | None:
    try:
        model = load_latest_model(
            Path(os.environ.get("MLFLOW_TRACKING_DIR", "mlruns")),
            os.environ.get("MLFLOW_EXPERIMENT", "churn"),
        )
    except LookupError:
        return None
    return ChurnPredictor(model)


def create_app(
    repository: CustomerRepository | None = None, predictor: ChurnPredictor | None = None
) -> FastAPI:
    """Build the app. Pass dependencies explicitly in tests; defaults come from the environment."""

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        app.state.repository = repository or CustomerRepository(
            Path(os.environ.get("DUCKDB_PATH", "data/warehouse.duckdb"))
        )
        app.state.predictor = predictor or (None if repository else _load_default_predictor())
        yield

    app = FastAPI(title="Customer 360 API", version="0.1.0", lifespan=lifespan)

    @app.get("/health", response_model=HealthOut)
    def health(predictor: Predictor) -> HealthOut:
        return HealthOut(status="ok", model_loaded=predictor is not None)

    @app.get("/customers", response_model=list[CustomerOut])
    def list_customers(
        repository: Repository,
        segment: Segment | None = None,
        at_risk: bool | None = None,
        limit: Annotated[int, Query(ge=1, le=1000)] = 50,
    ) -> list[dict[str, object]]:
        return repository.list_customers(segment, at_risk, limit)

    @app.get("/customers/{customer_id}", response_model=CustomerOut)
    def get_customer(customer_id: str, repository: Repository) -> dict[str, object]:
        customer = repository.get_customer(customer_id)
        if customer is None:
            raise HTTPException(404, f"Customer '{customer_id}' not found")
        return customer

    @app.post("/predict/churn", response_model=ChurnPredictionOut)
    def predict_churn(
        body: PredictRequest, repository: Repository, predictor: Predictor
    ) -> ChurnPredictionOut:
        if predictor is None:
            raise HTTPException(503, "Churn model is not loaded")
        features = repository.get_features(body.customer_id)
        if features.empty:
            raise HTTPException(404, f"Customer '{body.customer_id}' not found")
        return ChurnPredictionOut(
            customer_id=body.customer_id, churn_probability=predictor.predict(features)
        )

    return app
