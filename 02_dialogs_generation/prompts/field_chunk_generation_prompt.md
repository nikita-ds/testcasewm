You will generate the NEXT CHUNK of an advisor-client conversation AND produce inline evidence for specific source fields.

GOAL
- Continue the conversation naturally from transcript_so_far.
- The advisor must ask questions that elicit the target fields.
- The clients must answer using the provided source_value.
  Rounded/ranged wording is allowed for realism, but every target's canonical source_value must also appear at least once exactly.
- Output BOTH the chunk utterances and an evidence_items list mapping each target_id to a short excerpt.

TARGETS_JSON FORMAT (IMPORTANT)
- targets_json is an array of objects with keys:
  - target_id
  - record_type (households/people/income_lines/assets/liabilities/protection_policies)
  - field (human label)
  - kind (money|number|date|interest_rate|text)
  - source_value (the canonical value to be covered in dialogue)
- These are already sanitized for prompting; NEVER output any internal schema tokens.

CRITICAL FORMAT REQUIREMENTS
- Output MUST be valid JSON only. No markdown. No commentary.
- Output MUST be a single JSON OBJECT with keys: "utterances", "evidence_items".
- One utterance per line.
- Each utterance MUST start with exactly one of these prefixes:
  - "Advisor:"
  - "{{client1_label}}"
  - "{{client2_label}}" (only if household_type == couple)

NAME USAGE (IMPORTANT)
- Use the client names inside the utterance text for natural addressing.
  - For example: "So tell me about you, {{client1_name}}." or "Thanks, {{client2_name}}."
- Do NOT address someone as "Client 1" / "Client 2" in normal conversation.
  - Exception: if you are explicitly confirming the labeling for `people[...].client_no`, you MAY say "Client 1" / "Client 2" once.

REALISM + PACING RULES (STRICT)
- Natural spoken English, imperfect: hesitations, self-corrections, interruptions.
- Clients usually speak in 1–2 sentences.
- Do not dump all targets in one long advisor monologue; ask, get answer, move on.
- You MAY interleave targets, but every target must be covered.
- Never include timestamps.

"LIVELINESS" BEATS (DOSE CONTROL)
- Do NOT force a misunderstanding / disagreement / tangent in every chunk.
- In THIS chunk, include AT MOST ONE of the following beats (0 or 1 is fine):
  1) a mild disagreement or correction between clients (or client corrects advisor)
  2) an interruption / overlap (a cut-in mid-thought)
  3) a small misunderstanding of a concept (e.g., gross vs net, balance vs payment) that gets resolved
- If transcript_so_far already contains a recent misunderstanding or correction, prefer to skip these beats.
- Only do a "going back to..." return-to-prior-topic line if it genuinely helps; do not add it by default.

REALISM SIGNALS (MATCH THE JUDGE)
- Imperfect memory is normal: clients should sometimes hedge ("I think", "roughly", "I'd have to check").
- Numeric recall style should sound human: sometimes "about 38k" instead of always exact formal phrasing.
- Emotional texture is normal: clients may SOMETIMES sound tired, impatient, or mildly irritated (no rudeness).
  - The advisor should acknowledge briefly ("Totally get it" / "I hear you"), then steer back to the question.
- Include at least one micro-repair per chunk (a quick self-correction or clarification).
- Allow one indirect answer that gets specific after a follow-up.
- Avoid stitched feel: reference the immediate prior context lightly ("as you said earlier…", "going back to…") without introducing new facts.

DOSE TARGETS (CONFIG)
- Target density for BOTH misunderstandings and recap/check-back moments:
  within the last {{recap_window_utterances}} utterances, allow at most {{recap_max_per_window}} recap/check-back moment(s).
  within the last {{misunderstanding_window_utterances}} utterances, allow at most {{misunderstanding_max_per_window}} misunderstanding moment(s).
  If transcript_so_far already includes one within the recent window, skip adding another in this chunk.

STYLE TARGET (DERIVED FROM THE EXEMPLAR TRANSCRIPTS)
- Short, messy, realistic turn-taking: lots of "yeah/okay/right" backchannel and occasional interruptions.
- Frequent micro-clarifications: the advisor re-phrases; the client answers loosely first, then tightens after a follow-up.
- Light disfluency: repeats, "sorry", "hang on", "I mean—", and sentence fragments are normal.
- Add tiny FACT-SAFE "admin" beats as connective tissue (1–2 per chunk max): "Let me note that down", "One sec", "Okay—go ahead".
- Optional tiny tangent (1–3 turns) like weather/commute/scheduling, then return.

ABSOLUTE NO-GOS (IMPORTANT)
- Do NOT include timestamps.
- Do NOT ask for or mention any PII: Social Security numbers, full addresses, account numbers, passwords, emails, phone numbers.

HARD BAN ON "SCHEMA TOKENS" IN UTTERANCES
- Never output snake_case tokens (words containing underscores), dotted keys, bracketed paths, internal IDs, or internal table/field names.
- If source_value is an enum-like concept, express it in natural spoken English (e.g., "married", "primary residence", "advisor platform", "RIA").

AVOID SYNTHETIC TELLS
- Avoid robotic advisor summaries and checklist-like cadence.
- Avoid abrupt topic jumps; use one short transitional line when switching target groups.
- Avoid unnaturally tidy, perfectly complete answers in one turn.

ANTI "TRAINING SCRIPT" CONSTRAINTS (HIGH PRIORITY)
- Do NOT narrate your process or teach another advisor how to do the job.
  Avoid meta phrases like: "for the record", "for compliance", "my worksheet", "the software asks", "I need to categorize this", "on our side".
- Keep clarifications short. If a misunderstanding happens, resolve it in 1–2 turns, then move on.
- Do NOT repeatedly restart the conversation with the same filler line (e.g., avoid repeating "before we jump in, how's your week been?").

ANTI "OVER-COACHING" / REAL-WORLD DOSAGE (HIGH PRIORITY)
- Avoid demonstrating every "perfect technique" (reframing, probing, assumption-checking) on every numeric detail.
  Default to pragmatic pacing: ask, get the number, confirm once, move on.
- If a classification debate drags ("is it a loan or a card", "gross vs net", "balance vs payment"), let a client occasionally push back.
  Example vibe (do not copy literally): "Can we just call it debt of about 2.5k and keep going?"
  The advisor should accept, write it down in the simplest truthful form, and proceed.

REALISTIC RESPONSE LATENCY (IMPORTANT)
- Do NOT make the advisor instantly produce precise numeric answers out of nowhere.
  If the advisor is about to restate a precise figure (especially totals), add a quick beat first (1 line max):
  "One sec—let me note that" / "Hang on, I'm just writing this down" / "Let me check I heard you right".
- Prefer that precise numbers originate from client speech, with the advisor echoing/confirming them, not "calculating" them.

GROUNDING RULES
- Use ONLY the provided source_value(s) for targets.
- Do NOT invent new numbers.
- When stating dollar amounts, you may add human formatting (e.g., $ and commas) as long as digits are unchanged.
  You may also use rounded/ranged phrasing ("about", "roughly", "between") for realism, but ensure the exact source_value is stated at least once.
  Do not introduce cents unless they are present in source_value.
- It is ok to round or provide a range around the source_value; if you do, mark status="approximate".
- Do not mention any record IDs or field paths in the utterances.

CANONICAL MENTION RULE (STRICT)
- For EACH target: ensure that at least one client utterance states the source_value in its exact canonical form.
  You may additionally include an approximate phrasing elsewhere.
- If you temporarily say a wrong numeric value, you MUST correct it explicitly within the next 1–3 utterances and still state the canonical source_value exactly.

NO BACKEND LABELS IN SPOKEN DIALOGUE
- Do NOT expose backend labels (asset type/provider type/subtype/ownership/classification) or internal field names.
- Express categories in natural English without reading internal labels aloud.

CORRECTIONS + CONFIRMATION (CRITICAL FOR VALIDATION)
- You MAY have a client initially guess a number imprecisely or even say a wrong number.
- If any number is stated imprecisely or incorrectly, you MUST later correct it explicitly in this chunk.
- Check-backs are useful but expensive.
  Only do ONE short check-back near the end of the chunk IF:
  (a) you covered multiple new numeric targets in this chunk, AND
  (b) transcript_so_far does NOT already contain a recent recap/check-back.
  Keep it to 1–2 utterances total; do not do multiple recap blocks.
- Even if a client pushes to move on, ensure the final captured phrasing contains ONE clear, easy-to-validate mention of each key numeric target.

ANTI-REPETITION (HIGH PRIORITY)
- Do NOT re-state the same exact numeric value over and over.
  As a rule of thumb: once a canonical number has been stated clearly, avoid repeating it more than 1 additional time in this chunk.
- Avoid the template loop: ask → answer → advisor repeats full number → client repeats full number.
  Prefer short confirmations: "Got it." / "Okay." / "Right." / "Yep." without re-saying the digits.
- After first mention, refer back with pronouns: "that payment", "that balance", "the policy", "the account".
- Never use the phrase "Quick check-back".

STABILITY RULES (for easier validation)
- Prefer covering quantitative/value targets first (amounts, balances, monthly costs), then descriptive details (provider/type/owner).
- When a target source_value is a number, try to say it in a simple form close to the input (e.g., "$38,200" or "about 38k").

RATE FORMAT (IMPORTANT)
- If a target has kind="interest_rate", ALWAYS speak it as a percentage (e.g., "4.9%" or "about five percent") and keep it close to source_value.
- In evidence_items: if you stated the source_value (or a tight human rounding), status must be "present" or "approximate" — never "contradiction".

SPECIAL CASES (TO PREVENT FALSE FAILURES)
- If targets_json includes a target with field "number of adults", you MUST explicitly ask and answer the adult count in plain language.
  Example style (adapt to household_type):
  - Advisor: "Just to confirm, is it just the two of you—two adults in the household?"
  - Client: "Yes, two adults."
- If targets_json includes any target with field "client label", you MUST explicitly confirm the client labeling (Client 1 / Client 2) in the utterances.
  Do not imply it indirectly; say it explicitly.
  Do NOT describe any internal coding (no zero-indexing). Use only the natural labels "Client 1" / "Client 2".

EVIDENCE RULES
- You MUST return exactly one evidence_items entry per input target, with the SAME target_id.
- evidence_text MUST be copied verbatim from your own utterances.
- evidence_text should include at least 1 advisor question and at least 1 client answer.
- Prefer selecting evidence_text that includes the exact canonical source_value mention for that target.
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

- client1_name: {{client1_name}}
- client2_name: {{client2_name}}

OPENING (if transcript_so_far is empty)
- Start with a natural greeting + a quick advisor intro and an invitation to speak.
- Use the client name(s) in-text (not as prefixes).
- Example vibe (do not copy literally): "So let me introduce myself…" then "Tell me about you, <name>."

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
- HARD LIMIT: NEVER output more than 75 utterances.
- HARD MINIMUM: output at least 12 utterances unless transcript_so_far is already very long or you are close to a global max-turns cap.
- Prefer 18–40 utterances.
- Keep evidence_text short (2–6 lines typically).
