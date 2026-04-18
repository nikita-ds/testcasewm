You will generate ONE PHASE of a long advisor-client conversation.

CRITICAL FORMAT REQUIREMENTS
- Output MUST be valid JSON only. No markdown. No commentary.
- One utterance per line.
- Each utterance MUST start with exactly one of these prefixes:
  - "Advisor:"
  - "{{client1_label}}"
  - "{{client2_label}}" (only if household_type == couple)
- Natural spoken English, imperfect: hesitations ("uh"), self-corrections, interruptions, clarifications.
- Do not be overly polished.

GROUNDING REQUIREMENTS
- The dialogue must be grounded in the provided financial_profile_digest and scenario.
- Do NOT invent new numbers. You may round, paraphrase, or reference ranges.
- If a detail is missing, ask a question instead of fabricating.
- Personas must influence behavior consistently.
- Use ONLY facts belonging to this household. Do not mix with other households.
- The transcript must NOT contain any record IDs.

INPUTS
- scenario_name: {{scenario_name}}
- household_type: {{household_type}}
- phase_index: {{phase_index}}
- phase_name: {{phase_name}}
- phase_json:
{{phase_json}}
- outline_json:
{{outline_json}}
- personas_json:
{{personas_json}}
- state_json:
{{state_json}}
- transcript_so_far (may be empty; last ~200 lines only):
{{transcript_so_far}}
- financial_profile_digest (compact, includes record IDs for coverage tracking):
{{financial_profile_digest}}

- valid_record_ids_json (ONLY these IDs are valid for this household):
{{valid_record_ids_json}}

OUTPUT JSON SCHEMA
{
  "utterances": ["Speaker: ...", ...],
  "phase_notes": {
    "covered_topics": [strings],
    "misunderstandings": [strings],
    "followups_created": [strings],

    "used_person_ids": [strings],
    "used_income_line_ids": [strings],
    "used_asset_ids": [strings],
    "used_liability_ids": [strings],
    "used_policy_ids": [strings]
  }
}

COVERAGE / ANTI-MIXING RULES (STRICT)
- Every time you meaningfully reference a specific person / income line / asset / liability / policy from the digest, add its ID to the corresponding used_*_ids list.
- The used_*_ids lists must be subsets of valid_record_ids_json.
- Do NOT output IDs in utterances; IDs are for phase_notes only.

TARGET LENGTH
- Aim for phase_json.target_turns utterances.
- If transcript_so_far is long and max_turns is likely to be reached soon, end the phase with a natural stopping point.

REALISM CHECKLIST
- Include at least one brief repetition or re-ask.
- Include at least one clarification or repair.
- Include at least one moment of slight topic drift and return.
- For couples: include at least one interaction between clients (agreement/disagreement, correction, interruption).
{{example_transcripts}}
