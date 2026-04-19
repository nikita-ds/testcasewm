You will create a multi-phase outline for a long, realistic financial advisor conversation.

CRITICAL REQUIREMENTS
- Output MUST be valid JSON only. No markdown. No commentary.
- Do NOT generate the full dialogue here.
- Must be grounded in the provided financial profile and scenario.
- The conversation must feel natural: repetitions, clarifications, small misunderstandings, topic drift and return.
- Conversational rounding/ranges are allowed for realism, but you must plan that every canonical numeric value will be stated exactly at least once somewhere in the final conversation.

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
- Use 4–6 phases (prefer fewer phases for faster generation).
- total_target_turns must be between min_turns and max_turns.
- Sum of phases.target_turns should approximately equal total_target_turns.
- Keep individual phase target_turns small (typically 15–45) to reduce runtime and the risk of truncated JSON outputs.
- Include at least 2 planned moments where the conversation returns to an earlier topic.
- Include at least 1 planned misunderstanding (term confusion) and a repair.
- Include at least 1 planned moment of disagreement/negotiation (especially for couples).
- Make sure the outline covers: goals/objectives, income/cashflow, expenses, debts, investable assets mix, property, risk tolerance, tax bracket band, protection policies (if present), next steps.

PACE / BREVITY (IMPORTANT)
- Keep phase names and bullets short.
- Prefer concrete coverage over long storytelling in the outline.
- HARD LIMITS (STRICT):
  - phase_name: max 12 words
  - objectives: 2–4 items, each max 10 words
  - must_cover_topics: 3–6 items, each max 10 words
  - realism_hooks: 2–4 items, each max 10 words
  - Do NOT add any extra keys beyond the schema.

REALISM REQUIREMENTS (ADD AS HOOKS)
- Plan at least 2 moments of imperfect recall where a client says they don't remember exactly and answers with a range ("between X and Y", "around", "I'd have to check").
  Ensure the outline also includes a later moment where the exact canonical value is stated clearly.
- Plan expense discovery so it unfolds over multiple back-and-forth turns; avoid a single "here are all our expenses" dump.
  - Include at least one moment where an expense category is initially missed (e.g., childcare, insurance, subscriptions, irregular repairs) and is remembered later after a prompt.
- Plan 0–2 brief tangents / small-talk "water" moments TOTAL across the whole conversation.
  Keep them organic (traffic/parking/weather) and avoid making them feel like checklist items.

ADDITIONAL PROMPT INSTRUCTIONS (STYLE / REALISM)
- Avoid repetitive phrasing and template loops.
  Do NOT plan repeated bridge lines like "How's your week been?" multiple times.
- Do NOT plan frequent recap/check-back blocks after every section.
  Plan at most 1–2 short recap moments across the whole conversation, at natural breaks.
- If you plan a "labels in the system" confirmation (Client 1/Client 2), plan it ONCE early, resolve within 2–3 exchanges, and never revisit.
- In couples, plan complementary personalities:
  - one more detail-oriented "numbers person" who corrects
  - one who speaks in round numbers and occasionally mixes up terms (not constantly)

COVERAGE REQUIREMENT (STRICT)
- The final conversation must explicitly discuss EVERY record listed in valid_record_ids_json across the phases.
- Plan at least one phase that systematically reviews and confirms:
  - every income line
  - every asset account
  - every liability
  - every protection policy (if any)
