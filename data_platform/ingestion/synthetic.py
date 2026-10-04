"""Synthetic bronze-layer data with realistic statistical properties.

All assumptions live in :class:`SyntheticConfig`. They are plausible B2B SaaS
parameters. Every generator is a pure function of its
inputs and ``seed``, so runs are reproducible.
"""

from dataclasses import dataclass, field
from datetime import date

import numpy as np
import pandas as pd

SEGMENTS = ("SMB", "MID_MARKET", "ENTERPRISE")
INDUSTRIES = ("Manufacturing", "Retail", "Finance", "Healthcare", "Technology", "Logistics")


@dataclass(frozen=True)
class SyntheticConfig:
    # Customer base: most customers are small, a few are very large.
    segment_weights: tuple[float, float, float] = (0.60, 0.30, 0.10)
    # Median headcount and log-normal sigma per segment (long right tail).
    employees_median: tuple[float, float, float] = (40.0, 400.0, 5_000.0)
    employees_sigma: tuple[float, float, float] = (0.6, 0.5, 0.6)
    industry_null_share: float = 0.04
    # Contracts.
    contract_start_min: date = date(2022, 1, 1)
    contract_start_days: int = 1_095
    term_months: tuple[int, int, int] = (12, 24, 36)
    term_probabilities: tuple[float, float, float] = (0.55, 0.30, 0.15)
    fee_per_employee: tuple[float, float, float] = (8.0, 6.0, 4.0)  # volume discount
    fee_sigma: float = 0.25
    # Daily usage.
    usage_per_employee: float = 2.0
    customer_level_sigma: float = 0.30
    weekend_factor: float = 0.55
    daily_trend_mean: float = 0.0005
    daily_trend_sigma: float = 0.001
    daily_noise_sigma: float = 0.15
    spike_probability: float = 0.003
    spike_range: tuple[float, float] = field(default=(2.0, 4.0))


DEFAULT_CONFIG = SyntheticConfig()


def generate_customers(n: int, seed: int, config: SyntheticConfig = DEFAULT_CONFIG) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    segment_idx = rng.choice(len(SEGMENTS), size=n, p=config.segment_weights)
    median = np.array(config.employees_median)[segment_idx]
    sigma = np.array(config.employees_sigma)[segment_idx]
    employees = np.maximum(1, np.rint(rng.lognormal(np.log(median), sigma))).astype(int)

    industry = rng.choice(np.array(INDUSTRIES, dtype=object), size=n)
    industry[rng.random(n) < config.industry_null_share] = None

    return pd.DataFrame(
        {
            "customer_id": [f"C{i:06d}" for i in range(n)],
            "segment": np.array(SEGMENTS, dtype=object)[segment_idx],
            "employees": employees,
            "industry": industry,
        }
    )


def generate_contracts(
    customers: pd.DataFrame, seed: int, config: SyntheticConfig = DEFAULT_CONFIG
) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    n = len(customers)
    start = pd.Timestamp(config.contract_start_min) + pd.to_timedelta(
        rng.integers(0, config.contract_start_days, size=n), unit="D"
    )
    term = rng.choice(config.term_months, size=n, p=config.term_probabilities)
    segment_idx = customers["segment"].map({s: i for i, s in enumerate(SEGMENTS)}).to_numpy()
    base_fee = customers["employees"].to_numpy() * np.array(config.fee_per_employee)[segment_idx]
    fee = base_fee * rng.lognormal(0.0, config.fee_sigma, size=n)

    return pd.DataFrame(
        {
            "customer_id": customers["customer_id"].to_numpy(),
            "start_date": start,
            "end_date": start + pd.to_timedelta(term * 30, unit="D"),  # 30-day months
            "term_months": term,
            "monthly_fee": np.round(fee, 2),
        }
    )


def generate_usage(
    customers: pd.DataFrame,
    start: date,
    days: int,
    seed: int,
    config: SyntheticConfig = DEFAULT_CONFIG,
) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    n = len(customers)
    dates = pd.date_range(start, periods=days, freq="D")

    level = (
        customers["employees"].to_numpy()
        * config.usage_per_employee
        * rng.lognormal(0.0, config.customer_level_sigma, size=n)
    )
    trend = rng.normal(config.daily_trend_mean, config.daily_trend_sigma, size=n)
    growth = np.exp(np.outer(trend, np.arange(days)))
    seasonality = np.where(dates.dayofweek >= 5, config.weekend_factor, 1.0)
    noise = rng.lognormal(0.0, config.daily_noise_sigma, size=(n, days))
    spikes = np.where(
        rng.random((n, days)) < config.spike_probability,
        rng.uniform(*config.spike_range, size=(n, days)),
        1.0,
    )
    usage = level[:, None] * growth * seasonality[None, :] * noise * spikes

    return pd.DataFrame(
        {
            "customer_id": np.repeat(customers["customer_id"].to_numpy(), days),
            "usage_date": np.tile(dates.to_numpy(), n),
            "daily_usage": np.round(usage.ravel(), 3),
        }
    )
