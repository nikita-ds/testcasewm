from __future__ import annotations

from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field, RootModel


HouseholdType = Literal["single", "couple"]


class PersonaProfile(BaseModel):
    name: Optional[str] = None
    age: int = Field(..., ge=18, le=95)
    role_in_household: str
    financial_literacy_level: str
    risk_attitude_behavioral: str
    communication_style: str
    personality_traits: List[str] = Field(..., min_length=2, max_length=4)
    emotional_tendencies: List[str] = Field(..., min_length=1, max_length=3)
    decision_making_style: str
    trust_level_toward_advisor: str
    internal_biases: List[str] = Field(default_factory=list)
    hidden_concerns: List[str] = Field(default_factory=list)


class Persona(BaseModel):
    id: Literal["client_1", "client_2"]
    profile: PersonaProfile


class Personas(RootModel[List[Persona]]):
    pass


class OutlinePhase(BaseModel):
    phase_name: str
    objectives: List[str]
    must_cover_topics: List[str]
    target_turns: int = Field(..., ge=6, le=1200)
    realism_hooks: List[str] = Field(default_factory=list)


class ConversationOutline(BaseModel):
    household_type: HouseholdType
    total_target_turns: int = Field(..., ge=40, le=5000)
    phases: List[OutlinePhase]


class PhaseNotes(BaseModel):
    covered_topics: List[str] = Field(default_factory=list)
    misunderstandings: List[str] = Field(default_factory=list)
    followups_created: List[str] = Field(default_factory=list)
    used_person_ids: List[str] = Field(default_factory=list)
    used_income_line_ids: List[str] = Field(default_factory=list)
    used_asset_ids: List[str] = Field(default_factory=list)
    used_liability_ids: List[str] = Field(default_factory=list)
    used_policy_ids: List[str] = Field(default_factory=list)


class PhaseGenerationResult(BaseModel):
    utterances: List[str]
    phase_notes: PhaseNotes = Field(default_factory=PhaseNotes)


class ConversationStateModel(BaseModel):
    confirmed_facts: Dict[str, Any] = Field(default_factory=dict)
    open_questions: List[str] = Field(default_factory=list)
    repeated_concerns: List[str] = Field(default_factory=list)
    misunderstood_terms: List[str] = Field(default_factory=list)
    emotional_tone: Dict[str, str] = Field(default_factory=dict)


class StateUpdateResult(BaseModel):
    state: ConversationStateModel
    phase_summary: str
    open_questions: List[str] = Field(default_factory=list)
