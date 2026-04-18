from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict


class BaseRow(BaseModel):
    model_config = ConfigDict(extra="allow")


class HouseholdRow(BaseRow):
    household_id: str
    scenario: str
    country: str
    market: str

    annual_household_gross_income: float
    monthly_expenses_total: float
    investable_assets_total: float


class PersonRow(BaseRow):
    person_id: str
    household_id: str
    client_no: int
    role: str


class IncomeLineRow(BaseRow):
    income_line_id: str
    household_id: str


class AssetRow(BaseRow):
    asset_id: str
    household_id: str


class LiabilityRow(BaseRow):
    liability_id: str
    household_id: str


class ProtectionPolicyRow(BaseRow):
    policy_id: str
    household_id: str


class GeneratedHousehold(BaseModel):
    household: HouseholdRow
    people: List[PersonRow]
    income_lines: List[IncomeLineRow]
    assets: List[AssetRow]
    liabilities: List[LiabilityRow]
    protection_policies: List[ProtectionPolicyRow]
