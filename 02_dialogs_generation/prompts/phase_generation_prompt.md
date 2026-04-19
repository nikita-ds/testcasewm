You will generate ONE PHASE of a long advisor-client conversation.

CRITICAL FORMAT REQUIREMENTS
- Output MUST be valid JSON only. No markdown. No commentary.
- Output MUST be a single JSON OBJECT with keys "utterances" and "phase_notes". Do NOT output a JSON array.
- One utterance per line.
- Each utterance MUST start with exactly one of these prefixes:
  - "Advisor:"
  - "{{client1_label}}"
  - "{{client2_label}}" (only if household_type == couple)

NAME USAGE (IMPORTANT)
- Use the client names inside the utterance text for natural addressing.
  - For example: "So tell me about you, {{client1_name}}." or "Thanks, {{client2_name}}."
- Do NOT address someone as "Client 1" / "Client 2" in normal conversation.
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
- Include a small amount of "water" / filler: brief small talk, tiny admin beats, occasional checking understanding.
  Keep it light; do not create repetitive filler loops.
- Emotional texture is normal: clients may SOMETIMES sound tired, stressed, impatient, or mildly irritated (no rudeness).
  - The advisor should acknowledge it briefly and keep the meeting on track.
- Include at least one moment where someone answers indirectly first, then gets more specific after a follow-up.
- Never include timestamps (e.g., "[00:01:23]" or "0:01:23").

ANTI "TRAINING SCRIPT" CONSTRAINTS (HIGH PRIORITY)
- Do NOT sound like you're teaching another advisor. Avoid meta/process talk: "worksheet", "for the record", "compliance", "the software", "I need to categorize".
- Keep "definition lectures" minimal. If you explain a term (gross vs net, balance vs payment), do it in one short line.
- Avoid checklist cadence: do not do repeated multi-item recaps after every topic.

DOSE TARGETS (CONFIG)
- Target density for BOTH misunderstandings and recap/check-back moments:
  within the last {{recap_window_utterances}} utterances, allow at most {{recap_max_per_window}} recap/check-back moment(s).
  within the last {{misunderstanding_window_utterances}} utterances, allow at most {{misunderstanding_max_per_window}} misunderstanding moment(s).
  If transcript_so_far already includes one within the recent window, skip adding another in this phase.

ANTI-REPETITION (HIGH PRIORITY)
- Do NOT repeat the same exact numbers over and over.
  Once a canonical number has been stated clearly, avoid repeating it more than 1–2 additional times in this phase.
- Avoid the loop: advisor repeats full number → client repeats full number.
  Prefer short confirmations like "yeah" / "right" / "that's correct" without re-saying digits.
- Never use the phrase "Quick check-back".

ANTI "OVER-COACHING" / REAL-WORLD DOSAGE (HIGH PRIORITY)
- Do NOT demonstrate every counseling technique on every detail.
  Keep most numeric discovery to: ask → answer → one clarifying follow-up (optional) → move on.
- If you notice you're stuck in a loop (e.g., debating whether something is a credit card vs loan), allow a client to push back.
  The advisor should accept a simple truthful label ("debt" / "card" / "loan" as appropriate to the digest), capture the number, and keep going.
  If an approximate phrasing is used, ensure the canonical value is later stated exactly at least once.

REALISTIC RESPONSE LATENCY (IMPORTANT)
- Avoid "instant" perfect restatements of precise numbers by the advisor.
  When the advisor restates a precise figure, add a quick admin beat first (1 line max):
  "One sec—I'm writing that down" / "Hang on" / "Let me make sure I got that right".
- Prefer that precise numbers are said by clients; the advisor mostly echoes/organizes them.

CORRECTIONS + CONFIRMATION (CRITICAL FOR VALIDATION)
- You MAY have a client initially guess a number imprecisely or even say a wrong number.
- If any number is stated imprecisely or incorrectly, you MUST later correct it explicitly in the SAME phase.
- Corrections may clarify concepts (e.g., gross vs net, balance vs payment) but must NEVER alter canonical values.
- Do at most ONE short mid-phase check-back if needed.
- Make ONE FINAL restate/confirm near the end of the phase (brief, 2–4 items).

STYLE TARGET (DERIVED FROM synthetic_transcript1/2)
- The vibe is a real meeting/call: lots of short acknowledgements ("yeah", "right", "okay"), occasional overlaps, and incomplete sentences.
- Use light disfluency: repeats ("I—I"), self-corrections, "sorry", "hang on", and trailing dashes "—".
- Transitions often happen during tiny admin beats (FACT-SAFE): "Let me jot that down", "One second", "Okay—go ahead".
- Build facts via micro-clarifications: re-ask the same thing differently; confirm inclusions/exclusions; client starts vague then gets specific.
- Allow 1–2 short tangents (scheduling, call logistics, brief pleasantries), then return to the agenda.
  Avoid repetitive weather/traffic fillers.
- In couples: let them correct/interrupt each other once per phase.

ABSOLUTE NO-GOS (IMPORTANT)
- Do NOT ask for or mention any PII: Social Security numbers, full addresses, account numbers, passwords, emails, phone numbers.

GROUNDING REQUIREMENTS
- The dialogue must be grounded in the provided financial_profile_digest and scenario.
- Do NOT invent new numbers.
- You may round, paraphrase, or reference ranges for natural speech.
- However, every canonical numeric value that matters for grounding/coverage must appear at least once exactly as provided somewhere in the phase.
- If a detail is missing, ask a question instead of fabricating.
- Personas must influence behavior consistently.
- Use ONLY facts belonging to this household. Do not mix with other households.
- The transcript must NOT contain any record IDs.

NO BACKEND LABELS IN SPOKEN DIALOGUE
- Do NOT expose field paths, internal keys, or backend labels such as asset type, provider type, subtype, ownership field, or classification labels.
- If a categorical fact must be expressed, do so in natural English without reading backend labels aloud.

HARD BAN ON "SCHEMA TOKENS" IN UTTERANCES
- Never output snake_case tokens (words containing underscores), dotted keys, bracketed field paths, internal IDs, or internal table/field names.
- If an input value is an enum-like token, translate it into natural spoken English (e.g., "married", "primary residence", "advisor platform", "RIA").

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

- client1_name: {{client1_name}}
- client2_name: {{client2_name}}

OPENING (if transcript_so_far is empty)
- Start with a natural greeting + quick intro and invite the client(s) to talk.
- Use the client name(s) in-text.
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
- Include at most one moment of slight topic drift and return (skip if prior phases already had this).
- For couples: include at least one interaction between clients (agreement/disagreement, correction, interruption).
- Misunderstandings are optional per phase.
  If state_json.misunderstandings is already non-empty, prefer to NOT introduce a new misunderstanding in this phase.

FEW-SHOT STYLE GUIDANCE
- Read the injected STYLE EXEMPLARS below and imitate their pacing and imperfections.
- Do NOT copy names, facts, numbers, or any unique phrases from exemplars.
- Use exemplars only to learn conversational rhythm: interruptions, unfinished sentences, re-asks, clarifying questions.
{{example_transcripts}}
