You will update structured conversation state after a phase.

CRITICAL REQUIREMENTS
- Output MUST be valid JSON only. No markdown. No commentary.
- Do not invent facts. Only extract what was said or clearly implied.

INPUTS
- scenario_name: {{scenario_name}}
- household_type: {{household_type}}
- phase_index: {{phase_index}}
- phase_name: {{phase_name}}
- personas_json:
{{personas_json}}
- financial_profile_digest (compact; do not invent facts beyond it):
{{financial_profile_digest}}
- previous_state_json:
{{previous_state_json}}
- new_utterances:
{{new_utterances}}

OUTPUT JSON SCHEMA
{
  "state": {
    "confirmed_facts": {"key": "value", "...": "..."},
    "open_questions": [strings],
    "repeated_concerns": [strings],
    "misunderstood_terms": [strings],
    "emotional_tone": {"overall": "...", "client_1": "...", "client_2": "..."}
  },
  "phase_summary": string,
  "open_questions": [strings]
}

GUIDELINES
- Merge with previous_state_json instead of resetting.
- Keep keys short and consistent.
- Track repeated concerns (things clients come back to).
- Track misunderstood terms as STRINGS ONLY (e.g. "RMDs (repaired)", "asset allocation (not yet repaired)").
