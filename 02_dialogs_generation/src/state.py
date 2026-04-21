from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class ConversationState:
    confirmed_facts: Dict[str, Any] = field(default_factory=dict)
    open_questions: List[str] = field(default_factory=list)
    repeated_concerns: List[str] = field(default_factory=list)
    misunderstood_terms: List[str] = field(default_factory=list)
    emotional_tone: Dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "confirmed_facts": self.confirmed_facts,
            "open_questions": self.open_questions,
            "repeated_concerns": self.repeated_concerns,
            "misunderstood_terms": self.misunderstood_terms,
            "emotional_tone": self.emotional_tone,
        }


def default_state() -> ConversationState:
    return ConversationState(
        confirmed_facts={},
        open_questions=[],
        repeated_concerns=[],
        misunderstood_terms=[],
        emotional_tone={"overall": "neutral"},
    )
