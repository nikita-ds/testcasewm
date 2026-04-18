from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

from pydantic import BaseModel, Field


class GeneratorRuntimeConfig(BaseModel):
    n_households: int = Field(5000, ge=1)
    seed: int = 42
    priors_path: str = "artifacts/computed_priors.json"
    tables_dir: str = "artifacts/tables"


def load_generator_runtime_config(path: Optional[str]) -> GeneratorRuntimeConfig:
    if not path:
        return GeneratorRuntimeConfig()
    p = Path(path)
    if not p.exists():
        return GeneratorRuntimeConfig()
    data = json.loads(p.read_text(encoding="utf-8"))
    return GeneratorRuntimeConfig.model_validate(data)


class ValidationRuntimeConfig(BaseModel):
    priors_path: str = "artifacts/computed_priors.json"
    tables_dir: str = "artifacts/tables"
    expected_samples_seed: int = 123
    psi_bins: int = Field(10, ge=3, le=200)

    min_move_in_age_years: float = 18.0
    min_employment_start_age_years: float = 16.0
    max_mortgage_payment_to_income_ratio: float = 0.70


def load_validation_runtime_config(path: Optional[str]) -> ValidationRuntimeConfig:
    if not path:
        return ValidationRuntimeConfig()
    p = Path(path)
    if not p.exists():
        return ValidationRuntimeConfig()
    data = json.loads(p.read_text(encoding="utf-8"))
    return ValidationRuntimeConfig.model_validate(data)


class AnomaliesRuntimeConfig(BaseModel):
    tables_dir: str = "artifacts/tables"
    seed: int = 42

    features: list[str] = Field(
        default_factory=lambda: [
            "annual_household_gross_income",
            "monthly_expenses_total",
            "expense_to_income_ratio",
            "annual_alimony_paid",
            "loan_outstanding_total",
            "monthly_debt_cost_total",
            "monthly_mortgage_payment_total",
            "monthly_non_mortgage_payment_total",
            "mortgage_payment_to_income_ratio",
            "property_value_total",
            "investable_assets_total",
            "retirement_assets_total",
            "cash_and_cashlike_total",
            "alternatives_total",
            "net_worth_proxy",
            "num_dependants",
        ]
    )

    ae_hidden_dims: list[int] = Field(default_factory=lambda: [32, 16, 4])
    ae_batch_size: int = Field(128, ge=1, le=4096)
    ae_epochs: int = Field(40, ge=1, le=10000)
    ae_learning_rate: float = Field(1e-3, gt=0.0)

    iforest_n_estimators: int = Field(250, ge=1, le=5000)


def load_anomalies_runtime_config(path: Optional[str]) -> AnomaliesRuntimeConfig:
    if not path:
        return AnomaliesRuntimeConfig()
    p = Path(path)
    if not p.exists():
        return AnomaliesRuntimeConfig()
    data = json.loads(p.read_text(encoding="utf-8"))
    return AnomaliesRuntimeConfig.model_validate(data)
