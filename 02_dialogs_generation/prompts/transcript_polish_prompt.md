You will POLISH and EXPAND a transcript skeleton into a more natural advisor-client conversation.

GOAL
- Add light small-talk, confirmations, transitions, clarifying questions, and occasional minor misunderstandings.
- Keep the same facts and values as the skeleton. Do NOT add new factual content.
- Do NOT remove required factual lines; you may rephrase while preserving meaning.

CRITICAL REQUIREMENTS
- Output MUST be plain text only (NOT JSON).
- Each line must be exactly one utterance.
- Each utterance MUST start with exactly one of:
  - "Advisor:"
  - "Client 1:" (if household_type == couple)
  - "Client 2:" (if household_type == couple)
  - "Client:" (if household_type == single)
- Never include timestamps.
- Do not mention record IDs or field paths.
- When stating dollar amounts, round to the nearest $50 and never mention cents.

FACT PRESERVATION RULES (STRICT)
- Do not invent new numbers. Do not change numeric values.
- If you rephrase a number, keep it equivalent (e.g., "$40k" for 40000 is OK).
- Keep the ordering of topics roughly the same; you can add bridging lines between sections.

INPUTS
- household_type: {{household_type}}
- skeleton_transcript (verbatim):
{{skeleton_transcript}}

OUTPUT
- Return the polished transcript as plain text lines.
- Target expansion: +15% to +40% more lines than the skeleton.
- Keep client turns short (1–2 sentences usually).
