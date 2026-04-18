You will generate ONE PHASE of a long advisor-client conversation.

CRITICAL FORMAT REQUIREMENTS
- Output MUST be valid JSON only. No markdown. No commentary.
- Output MUST be a single JSON OBJECT with keys "utterances" and "phase_notes". Do NOT output a JSON array.
- One utterance per line.
- Each utterance MUST start with exactly one of these prefixes:
  - "Advisor:"
  - "{{client1_label}}"
  - "{{client2_label}}" (only if household_type == couple)
- Natural spoken English, imperfect: hesitations ("uh"), self-corrections, interruptions, clarifications.
- Do not be overly polished.

REALISM + PACING RULES (STRICT)
- Imperfect memory is normal. Clients SHOULD sometimes say things like:
  - "I don't remember exactly" / "I'd have to check" / "off the top of my head…"
  - give approximate answers: "around…", "roughly…", "between X and Y", "give or take".
- Client answers are usually NOT long.
  - Default to 1–2 sentences per client turn.
  - It is normal to have very short turns: "Yeah", "Right", "I think so", "Can you repeat that?".
  - Avoid client monologues unless the advisor explicitly asks them to walk through something step-by-step.
- Avoid "all answers immediately". Do not let any speaker dump a complete, perfectly organized list in one turn.
  - The advisor must ask follow-up questions and confirm step-by-step.
  - Clients should recall items gradually and sometimes add "Oh—also…" later.
- Expenses: do NOT list all expense categories at once.
  - Break expense discovery into multiple turns and categories (e.g., housing, utilities, food, healthcare, insurance, childcare, travel, subscriptions, taxes, irregular repairs).
  - It is normal for clients to forget categories (e.g., childcare) and mention them later when prompted.
- Include some "water" / filler: small talk, short tangents, checking understanding, non-substantive phrases.
- Include at least one moment where someone answers indirectly first, then gets more specific after a follow-up.
- Never include timestamps (e.g., "[00:01:23]" or "0:01:23").

GROUNDING REQUIREMENTS
- The dialogue must be grounded in the provided financial_profile_digest and scenario.
- Do NOT invent new numbers. You may round, paraphrase, or reference ranges.
- When stating dollar amounts, round to the nearest $50 and never mention cents.
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
- transcript_summary_so_far (rolling summary of prior phases; may be empty):
{{transcript_summary_so_far}}
- transcript_so_far (may be empty; recent window only):
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
- If phase_json contains remaining_record_ids, you MUST ensure every ID in remaining_record_ids appears in the corresponding used_*_ids list in phase_notes.
- Do NOT output IDs in utterances; IDs are for phase_notes only.

TARGET LENGTH
- Aim for phase_json.target_turns utterances.
- HARD LIMIT: NEVER output more than 60 utterances.
- Prefer 20–45 utterances unless phase_json.target_turns is smaller.
- If transcript_so_far is long and max_turns is likely to be reached soon, end the phase with a natural stopping point.

JSON SAFETY
- If you are running out of budget, end the phase early and close the JSON cleanly.
- Keep phase_notes lists short (usually 1–5 items each).

REALISM CHECKLIST
- Include at least one brief repetition or re-ask.
- Include at least one clarification or repair.
- Include at least one moment of slight topic drift and return.
- For couples: include at least one interaction between clients (agreement/disagreement, correction, interruption).

FEW-SHOT STYLE GUIDANCE
- Read the injected STYLE EXEMPLARS below and imitate their pacing and imperfections.
- Do NOT copy names, facts, numbers, or any unique phrases from exemplars.
- Use exemplars only to learn conversational rhythm: interruptions, unfinished sentences, re-asks, clarifying questions.
{{example_transcripts}}
