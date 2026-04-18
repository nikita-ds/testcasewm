You will create a multi-phase outline for a long, realistic financial advisor conversation.

CRITICAL REQUIREMENTS
- Output MUST be valid JSON only. No markdown. No commentary.
- Do NOT generate the full dialogue here.
- Must be grounded in the provided financial profile and scenario.
- The conversation must feel natural: repetitions, clarifications, small misunderstandings, topic drift and return.

INPUTS
- scenario_name: {{scenario_name}}
- household_type: {{household_type}}
- min_turns: {{min_turns}}
- max_turns: {{max_turns}}
- personas_json:
{{personas_json}}
- financial_profile_json:
{{financial_profile_json}}

- financial_profile_digest (compact summary; use this to ensure nothing is missed):
{{financial_profile_digest}}

- valid_record_ids_json (ONLY these records exist for this household; plan to cover all of them):
{{valid_record_ids_json}}

OUTPUT JSON SCHEMA
{
  "household_type": "single" | "couple",
  "total_target_turns": integer (between min_turns and max_turns),
  "phases": [
    {
      "phase_name": string,
      "objectives": [strings],
      "must_cover_topics": [strings],
      "target_turns": integer,
      "realism_hooks": [strings]
    }
  ]
}

GUIDELINES
- Use 6–12 phases (prefer more phases for longer conversations).
- total_target_turns must be between min_turns and max_turns.
- Sum of phases.target_turns should approximately equal total_target_turns.
- Keep individual phase target_turns reasonably sized (typically 80–250) to reduce the risk of truncated JSON outputs.
- Include at least 2 planned moments where the conversation returns to an earlier topic.
- Include at least 1 planned misunderstanding (term confusion) and a repair.
- Include at least 1 planned moment of disagreement/negotiation (especially for couples).
- Make sure the outline covers: goals/objectives, income/cashflow, expenses, debts, investable assets mix, property, risk tolerance, tax bracket band, protection policies (if present), next steps.

COVERAGE REQUIREMENT (STRICT)
- The final conversation must explicitly discuss EVERY record listed in valid_record_ids_json across the phases.
- Plan at least one phase that systematically reviews and confirms:
  - every income line
  - every asset account
  - every liability
  - every protection policy (if any)
