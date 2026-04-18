You will generate the NEXT CHUNK of an advisor-client conversation AND produce inline evidence for specific source fields.

GOAL
- Continue the conversation naturally from transcript_so_far.
- The advisor must ask questions that elicit the target fields.
- The clients must answer using the provided source_value (rounded/ranged wording is allowed).
- Output BOTH the chunk utterances and an evidence_items list mapping each target_id to a short excerpt.

CRITICAL FORMAT REQUIREMENTS
- Output MUST be valid JSON only. No markdown. No commentary.
- Output MUST be a single JSON OBJECT with keys: "utterances", "evidence_items".
- One utterance per line.
- Each utterance MUST start with exactly one of these prefixes:
  - "Advisor:"
  - "{{client1_label}}"
  - "{{client2_label}}" (only if household_type == couple)

REALISM + PACING RULES (STRICT)
- Natural spoken English, imperfect: hesitations, self-corrections, interruptions.
- Clients usually speak in 1–2 sentences.
- Do not dump all targets in one long advisor monologue; ask, get answer, move on.
- You MAY interleave targets, but every target must be covered.
- Never include timestamps.

GROUNDING RULES
- Use ONLY the provided source_value(s) for targets.
- Do NOT invent new numbers.
- When stating dollar amounts, round to the nearest $50 and never mention cents.
- It is ok to round or provide a range around the source_value; if you do, mark status="approximate".
- Do not mention any record IDs or field paths in the utterances.

STABILITY RULES (for easier validation)
- Prefer covering quantitative/value targets first (amounts, balances, monthly costs), then descriptive details (provider/type/owner).
- When a target source_value is a number, try to say it in a simple form close to the input (e.g., "$38,200" or "about 38k").

EVIDENCE RULES
- You MUST return exactly one evidence_items entry per input target, with the SAME target_id.
- evidence_text MUST be copied verbatim from your own utterances.
- evidence_text should include at least 1 advisor question and at least 1 client answer.
- If you fail to cover a target, set status="missing" and evidence_text="".

INPUTS
- dialog_id: {{dialog_id}}
- scenario_name: {{scenario_name}}
- household_type: {{household_type}}
- chunk_index: {{chunk_index}}

- personas_json:
{{personas_json}}

- financial_profile_digest:
{{financial_profile_digest}}

- targets_json (array):
{{targets_json}}

- transcript_so_far (recent window):
{{transcript_so_far}}

OUTPUT JSON SCHEMA
{
  "utterances": ["Speaker: ...", ...],
  "evidence_items": [
    {
      "target_id": "...",
      "status": "present|approximate|missing|contradiction",
      "evidence_text": "Advisor: ...\nClient...: ...",
      "notes": "optional short string"
    }
  ]
}

LENGTH LIMITS
- HARD LIMIT: NEVER output more than 45 utterances.
- Prefer 15–35 utterances.
- Keep evidence_text short (2–6 lines typically).
