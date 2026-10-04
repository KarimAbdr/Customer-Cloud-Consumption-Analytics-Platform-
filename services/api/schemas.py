from datetime import date
from typing import Literal

from pydantic import BaseModel

Segment = Literal["SMB", "MID_MARKET", "ENTERPRISE"]


class HealthOut(BaseModel):
    status: str
    model_loaded: bool


class CustomerOut(BaseModel):
    customer_id: str
    segment: Segment
    employees: int
    industry: str
    contract_end_date: date
    annual_contract_value: float
    avg_daily_usage: float
    usage_trend_ratio: float
    total_tickets: int
    is_at_risk: bool
    is_churned: bool


class PredictRequest(BaseModel):
    customer_id: str


class ChurnPredictionOut(BaseModel):
    customer_id: str
    churn_probability: float


class SegmentSummaryOut(BaseModel):
    segment: Segment
    customers: int
    at_risk: int
    annual_revenue_at_risk: float


class PortfolioSummaryOut(BaseModel):
    customers: int
    at_risk: int
    at_risk_share: float
    annual_revenue_at_risk: float
    segments: list[SegmentSummaryOut]


class PriorityCustomerOut(BaseModel):
    customer_id: str
    segment: Segment
    industry: str
    employees: int
    annual_contract_value: float
    churn_probability: float
    expected_loss: float
    usage_trend_ratio: float
    total_tickets: int
    signals: list[str]


class PriorityListOut(BaseModel):
    customers_scored: int
    total_expected_loss: float
    items: list[PriorityCustomerOut]
