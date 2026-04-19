You will generate SHORT BRIDGING utterances to connect two adjacent chunks of a transcript.

GOAL
- Insert a small amount of natural "banter" / "mumbling" / clarifications / minor disagreement.
- Smoothly transition from the previous topic to the next topic.
- Do NOT add any new facts, numbers, dates, or account details.

SAFE "WATER" YOU MAY ADD
- Very light small-talk that does NOT assert personal facts: scheduling, generic weekend plans, brief pleasantries.
  Avoid repetitive weather/traffic fillers.
- If you mention hobbies, keep it generic and non-committal (e.g., "Any hobbies keeping you busy lately?") and allow the client to answer vaguely.
- Do NOT claim a specific hobby/interest unless it already appears in the provided tail/head.

REALISM SIGNALS TO EMPHASIZE
- Natural uncertainty and memory behavior: brief "I think", "roughly", "off the top of my head", "I might be mixing that up".
- Micro-repairs: a speaker starts to say something, then corrects themselves without introducing new facts.
- Human pacing: short turns, quick acknowledgements, tiny side-comments.
- Organic transitions: the next topic should feel like a continuation of the same meeting, not a stitched jump.

EXEMPLAR-LIKE DELIVERY (HOW IT SHOULD SOUND)
- Lots of short acknowledgements: "yeah", "right", "okay", "got it".
- Occasional sentence fragments and overlaps.
- A "hang on" moment is okay, but keep it neutral and brief.

AVOID SYNTHETIC TELLS
- Do not sound like a template or a recap bot.
- Avoid overly neat summaries ("So to summarize...") unless it already appears in the provided tails/heads.
- Avoid repetitive filler (do not repeat the same phrase across multiple bridge lines).

CRITICAL OUTPUT REQUIREMENTS
- Output MUST be plain text only (NOT JSON).
- Each line is exactly one utterance.
- Each utterance MUST start with exactly one of:
  - "Advisor:"
  - "{{client1_label}}"
  - "{{client2_label}}" (only if household_type == couple)
- Never include timestamps.

FACT SAFETY (STRICT)
- Do not invent or change any numeric values.
- Do not introduce new assets/income/liabilities/policies.
- Avoid adding any concrete amounts, percentages, or dates.
- Do NOT ask for or mention any PII: Social Security numbers, full addresses, account numbers, passwords, emails, phone numbers.

STYLE
- Natural spoken English.
- Include 1–2 small imperfections: hesitation, self-correction, "uh", brief side comment.
- Optional: one brief client-to-client interaction (for couples), or a quick correction.

INPUTS
- household_type: {{household_type}}
- previous_chunk_tail (verbatim, last few utterances):
{{previous_chunk_tail}}

- next_chunk_head (verbatim, first few utterances):
{{next_chunk_head}}

- next_topic_hint: {{next_topic_hint}}

OUTPUT LENGTH
- Return 2–8 utterances. Prefer 3–6.
