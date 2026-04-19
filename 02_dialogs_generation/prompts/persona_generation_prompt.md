You will generate persona profiles for the household participants.

CRITICAL REQUIREMENTS
- Output MUST be valid JSON only. No markdown. No commentary.
- Create personas BEFORE dialogue generation.
- Personas must be consistent with the provided financial profile and scenario.
- Do not invent financial facts (income/assets/debts). If something is unknown, express it as a personality/behavioral tendency instead of fabricating a fact.

INPUTS
- scenario_name: {{scenario_name}}
- household_type: {{household_type}} ("single" or "couple")
- financial_profile_json:
{{financial_profile_json}}

- financial_profile_digest (compact summary):
{{financial_profile_digest}}

OUTPUT JSON SCHEMA
Return a JSON array of persona objects.

For household_type == "single": return exactly 1 item with id "client_1".
For household_type == "couple": return exactly 2 items with ids "client_1" and "client_2".

Each item:
{
  "id": "client_1" | "client_2",
  "profile": {
    "name": string|null,
    "age": integer (18..95),
    "role_in_household": string,
    "financial_literacy_level": string (include level and a short explanation),
    "risk_attitude_behavioral": string (behavioral, not just a label),
    "communication_style": string,
    "personality_traits": [2..4 short traits],
    "emotional_tendencies": [1..3 short tendencies],
    "decision_making_style": string,
    "trust_level_toward_advisor": string,
    "internal_biases": [0..N short biases],
    "hidden_concerns": [0..N short concerns]
  }
}

COUPLE DYNAMICS (if household_type == couple)
- Make the two clients meaningfully different.
- One may dominate; the other may defer or interrupt.
- Risk attitudes can differ; if they do, explain how it shows up in behavior.
- Ensure plausible alignment with financial profile (e.g., a higher-income split often implies more dominance, but not always).
- Prefer a complementary dynamic:
  - one is a "numbers person" who tends to remember specific figures and correct small inaccuracies
  - the other thinks in round numbers and occasionally mixes up terms (gross/net, premium/benefit, balance/payment)
  Keep misunderstandings believable and not constant; avoid caricature.

REALISM NOTES
- In "communication_style", explicitly encode how the client speaks in real meetings:
  - hedging ("maybe", "I think"), imperfect recall ("I don't remember exactly"), ranges ("between X and Y"), and occasional filler.
- Do not invent new financial facts; express uncertainty as behavior (e.g., "tends not to remember exact bill amounts").
