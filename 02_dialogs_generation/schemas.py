from __future__ import annotations

from typing import Any, Dict, List, Literal, Optional, Union

from pydantic import BaseModel, Field, RootModel


HouseholdType = Literal["single", "couple"]


RecordType = Literal[
    "households",
    "people",
    "income_lines",
    "assets",
    "liabilities",
    "protection_policies",
]


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
    target_turns: int = Field(..., ge=20, le=600)
    realism_hooks: List[str] = Field(default_factory=list)


class ConversationOutline(BaseModel):
    household_type: HouseholdType
    total_target_turns: int = Field(..., ge=200, le=2500)
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


class MisunderstoodTerm(BaseModel):
    term: str
    who: Optional[str] = None
    repaired: Optional[bool] = None
    context: Optional[str] = None


class ConversationStateModel(BaseModel):
    confirmed_facts: Dict[str, Any] = Field(default_factory=dict)
    open_questions: List[str] = Field(default_factory=list)
    repeated_concerns: List[str] = Field(default_factory=list)
    misunderstood_terms: List[Union[str, MisunderstoodTerm]] = Field(default_factory=list)
    emotional_tone: Dict[str, str] = Field(default_factory=dict)


class StateUpdateResult(BaseModel):
    state: ConversationStateModel
    phase_summary: str
    open_questions: List[str] = Field(default_factory=list)


EvidenceStatus = Literal["present", "approximate", "missing", "contradiction"]


class EvidenceTarget(BaseModel):
    target_id: str
    record_type: RecordType
    record_id: Optional[str] = None
    field_path: str
    source_value: Any


class EvidenceItem(BaseModel):
    target_id: str
    record_type: RecordType
    record_id: Optional[str] = None
    field_path: str
    source_value: Any
    status: EvidenceStatus
    evidence_text: str = ""
    notes: Optional[str] = None


class EvidenceExtractionBatchResult(BaseModel):
    items: List[EvidenceItem]


class InlineEvidenceItem(BaseModel):
    target_id: str
    status: EvidenceStatus
    evidence_text: str = ""
    notes: Optional[str] = None


class FieldChunkGenerationResult(BaseModel):
    utterances: List[str]
    evidence_items: List[InlineEvidenceItem]


class TranscriptRealismJudgeResult(BaseModel):
    candidate_probability_real: float = Field(..., ge=0.0, le=1.0)
    decision: Literal["very_likely_real", "likely_real", "uncertain", "likely_synthetic", "very_likely_synthetic"]
    strengths: List[str] = Field(default_factory=list)
    synthetic_tells: List[str] = Field(default_factory=list)
    comparison_to_negative_controls: List[str] = Field(default_factory=list)
    save_recommended: bool = False
    summary: str
