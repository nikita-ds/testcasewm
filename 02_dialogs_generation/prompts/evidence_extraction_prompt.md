You will extract verifiable EVIDENCE snippets from a generated advisor-client transcript.

GOAL
- For each target source field/value from the input financial profile, find a short excerpt in the transcript where the ADVISOR asks about it AND the CLIENT(S) provide the information.
- This will later be regex-checked against the original input values.

CRITICAL FORMAT REQUIREMENTS
- Output MUST be valid JSON only. No markdown. No commentary.
- Output MUST be a single JSON OBJECT with key "items".

HARD HONESTY RULES
- Do NOT invent evidence. Only use text that appears in the transcript.
- If you cannot find a good excerpt, mark status="missing" and leave evidence_text="".
- If the transcript mentions a rounded/range value instead of exact source_value, mark status="approximate" and include the mentioned text verbatim.
- If the transcript contradicts the source_value, mark status="contradiction" and include the contradictory excerpt.

WHAT COUNTS AS EVIDENCE
- evidence_text should contain:
  - at least 1 advisor question ("Advisor:")
  - at least 1 client answer ("Client" prefix)
- Keep evidence_text short: typically 2–6 lines copied verbatim.

INPUTS
- dialog_id: {{dialog_id}}
- household_id: {{household_id}}
- scenario_name: {{scenario_name}}
- household_type: {{household_type}}

- financial_profile_digest (for context):
{{financial_profile_digest}}

- evidence_targets_json: a JSON array of targets, each with:
  - target_id (string)
  - record_type (string)
  - record_id (string or null)
  - field_path (string)
  - source_value (any JSON)

{{evidence_targets_json}}

- transcript (verbatim):
{{transcript_text}}

OUTPUT JSON SCHEMA
{
  "items": [
    {
      "target_id": "...",
      "record_type": "households|people|income_lines|assets|liabilities|protection_policies",
      "record_id": "..." | null,
      "field_path": "...",
      "source_value": <any JSON>,
      "status": "present|approximate|missing|contradiction",
      "evidence_text": "Advisor: ...\nClient...: ...\n...",
      "notes": "optional short string"
    }
  ]
}

OUTPUT REQUIREMENTS
- Return exactly ONE item per input target, with the SAME target_id.
- Copy transcript lines verbatim into evidence_text.
- Do not include record IDs in evidence_text.
- Keep notes very short (0–1 sentence).
