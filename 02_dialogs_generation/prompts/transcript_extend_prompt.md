You are extending an existing advisor–client transcript to make it longer and more realistic.

GOAL
- Add more turns (lines) while keeping the existing facts unchanged.
- The added turns should feel like natural “water”: small talk, clarifications, admin beats, micro-repairs, confirming next steps.
- Do NOT introduce new numeric facts, new accounts, new employers, new debts, new assets, or new personal details.
- If you mention any number at all, it must be something already said in the transcript tail; otherwise avoid numbers entirely.

CORRECTIONS + CONFIRMATION
- You MAY add a brief misunderstanding or a quick misstatement, but if you do, you MUST correct it within the next 1–3 added lines.
- Avoid adding new recap loops.
  If you restate any key number, do it sparingly (ideally once), and prefer a very short confirmation that does NOT echo the full digits back.
  Do NOT add repeated "check-back" blocks if the transcript tail already has recent confirmations.

ANTI-REPETITION (HIGH PRIORITY)
- Never use the phrase "Quick check-back".
- Do not repeat the same bridge line across multiple added turns.
- Prefer non-numeric "water" lines; avoid re-saying digits unless absolutely necessary.

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

SMALL-TALK DOSAGE
- Avoid repetitive weather/traffic fillers.

ANTI "OVER-COACHING" / REAL-WORLD DOSAGE
- Do NOT add long loops of reframing/probing/assumption-checking.
  If you add clarification, keep it to 1 short question + 1 short answer, then move on.
- Allow occasional pragmatic client pushback if a topic is dragging, and let the advisor accept it and proceed.

REALISTIC RESPONSE LATENCY
- If you restate a precise number that already exists in the transcript tail, consider adding a tiny pacing beat first (1 line max):
  "One sec—I'm jotting that down" / "Hang on" / "Let me make sure I got that right".
  Do not add any new numbers.

ANTI "TRAINING SCRIPT" CONSTRAINTS
- Do NOT add meta/process narration ("for the record", "worksheet", "the software").
- Do NOT add repeated recap blocks; if you add a check-back, keep it to one short line.
- Avoid reusing the same bridge line multiple times (e.g., don't repeatedly say "before we jump in...").

NAME USAGE
- Use client names inside the utterance text when it feels natural:
  - {{client1_name}} and {{client2_name}}
- Do NOT change the speaker prefixes.

TARGET
- Add approximately {{target_new_turns}} new turns.
- The final transcript should aim for at least {{target_total_turns}} total turns, but never exceed {{max_total_turns}}.

CONTEXT (TRANSCRIPT TAIL)
{{transcript_tail}}
