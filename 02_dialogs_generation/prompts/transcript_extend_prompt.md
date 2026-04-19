You are extending an existing advisor–client transcript to make it longer and more realistic.

GOAL
- Add more turns (lines) while keeping the existing facts unchanged.
- The added turns should feel like natural “water”: small talk, clarifications, admin beats, micro-repairs, confirming next steps.
- Do NOT introduce new numeric facts, new accounts, new employers, new debts, new assets, or new personal details.
- If you mention any number at all, it must be something already said in the transcript tail; otherwise avoid numbers entirely.

CORRECTIONS + CONFIRMATION
- You MAY add a brief misunderstanding or a quick misstatement, but if you do, you MUST correct it within the added lines.
- If you restate any key number, prefer a short advisor "restate + confirm" and a client confirmation.

STRICT FORMAT
- Output ONLY the NEW lines you are adding (do not repeat existing lines).
- Each line MUST start with exactly one of:
  - Advisor:
  - {{client1_label}}
  - {{client2_label}}
- No timestamps. No bullet lists. No headings. No JSON.

SAFETY
- Do not output PII (no SSN, full address, phone numbers, emails, account numbers, passwords).

STYLE
- Keep turns short and conversational (fragments, backchannels, small repairs).
- Avoid template-y repetition and long monologues.
- Emotional texture is normal: clients may SOMETIMES sound tired, impatient, or mildly irritated (no rudeness).
  - The advisor should acknowledge briefly and keep things moving.

NAME USAGE
- Use client names inside the utterance text when it feels natural:
  - {{client1_name}} and {{client2_name}}
- Do NOT change the speaker prefixes.

TARGET
- Add approximately {{target_new_turns}} new turns.
- The final transcript should aim for at least {{target_total_turns}} total turns, but never exceed {{max_total_turns}}.

CONTEXT (TRANSCRIPT TAIL)
{{transcript_tail}}
