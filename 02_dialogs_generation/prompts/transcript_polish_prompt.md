You will FINALIZE a transcript skeleton into a much more realistic advisor-client conversation.

GOAL
- Make the dialogue feel close to a real discovery / fact-find meeting, not like stitched chunks.
- Expand the conversation noticeably while preserving all grounded facts already present in the skeleton.
- Increase realism through hesitation, uncertainty, partial recall, small corrections, and natural follow-up questions.

ANTI-REPETITION (HIGH PRIORITY)
- If the skeleton contains repeated loops (e.g., multiple "check-back" blocks, the same mortgage/payment/policy repeated many times), COMPRESS them.
- Keep at least ONE clear canonical mention of each grounded number, but avoid re-stating the same digits repeatedly.
- Avoid the pattern where both advisor and client restate the same number back-to-back.
  Prefer short confirmations ("yep", "right", "sounds right") without repeating digits.
- Never use the phrase "Quick check-back".

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
- Do NOT change any numeric digits that already exist in the skeleton.
  You may add an approximate restatement ("about", "roughly", ranges) for realism, but ensure the exact canonical number still appears clearly at least once.
- Do NOT ask for or mention any PII: Social Security numbers, full addresses, account numbers, passwords, emails, phone numbers.

NAME USAGE (IMPORTANT)
- Use the provided client name(s) inside the utterance text for natural addressing.
- Do NOT change the speaker prefixes.

FACT PRESERVATION RULES (STRICT)
- Do not invent new accounts, policies, debts, dates, family members, employers, or numeric facts.
- Do not change the meaning of existing numbers.
- If the skeleton gives a total expense number, you may unpack how the client remembers it into separate categories only if the categories are explicitly framed as a recall process and still consistent with the known totals.
- Do not remove required factual lines; you may rewrite them into more natural speech while preserving meaning.
- When you compress repetitive loops, do NOT delete the only explicit mention of a grounded number.
  Ensure each key numeric fact from the skeleton still appears at least once in clear, easy-to-validate wording.

CORRECTIONS + CONFIRMATION (CRITICAL FOR VALIDATION)
- You MAY add imperfect recall moments ("I think", "roughly", "maybe") and brief misstatements.
- If you introduce an imprecise or wrong numeric phrasing, you MUST later restate the correct grounded number
  (from the skeleton) explicitly, and have the client(s) confirm.

NO BACKEND LABELS IN SPOKEN DIALOGUE
- Do NOT expose backend labels (asset type/provider type/subtype/ownership/classification) or internal field names.
- Express categories in natural English without reading internal labels aloud.

SCHEMA-LEAK CLEANUP (REQUIRED)
- If the skeleton contains any schema/internal tokens (snake_case words with underscores, dotted keys, bracketed paths, internal IDs), you MUST rewrite them into natural spoken English.
- Keep all numeric digits and dates exactly the same when rewriting.

REALISM SIGNALS TO ADD
- Clients should sometimes sound unsure: "I think", "roughly", "off the top of my head", "let me think", "that sounds about right".
- Let clients remember spending in pieces, not only in one grand total:
  for example housing/taxes/utilities, groceries, transport, insurance, subscriptions, child-related costs, travel, home upkeep.
- Include evaluative judgments while recalling magnitudes:
  examples of the style, not literal text: "that feels high", "that's not too bad", "it's probably our biggest monthly hit", "the maintenance is small unless something breaks".
- Allow mild self-corrections and partner corrections in couple conversations.
- Add brief advisor reactions that sound human: checking understanding, reframing, sanity-checking whether a figure is fixed vs variable, and separating essential vs discretionary costs.
- Keep transitions organic so the dialogue does not feel chunked or templated.

STYLE TARGET (DERIVED FROM synthetic_transcript1/2)
- Lots of backchannel and fragments: "yeah", "right", "okay", "mm", with occasional overlaps.
- Light disfluency: repeats ("I—I"), self-corrections, "sorry", "hang on", and trailing dashes "—".
- Use small admin beats to hide stitching: "Let me write that down", "one second", "okay—go ahead".
- Small talk often pops up during admin moments (FACT-SAFE): scheduling, generic weekend plans, brief pleasantries.
  Avoid repetitive weather/traffic fillers.
- Mild pushback and repair is normal: a client challenges, advisor reassures, then returns to the agenda.
- Emotional texture is normal: clients may SOMETIMES sound tired, stressed, or mildly irritated (no rudeness).
  - The advisor should acknowledge briefly and steer back to facts.

LIGHT SMALL-TALK (SAFE "WATER")
- Add 0–2 brief human moments across the transcript: scheduling, generic weekend plans, brief pleasantries.
  Avoid repetitive weather/traffic fillers.
- If you include hobbies, do it as a generic question + vague answer (no specific hobby facts) unless the skeleton already mentions a specific hobby.
- Keep these moments short (1–3 turns each) and naturally return to the agenda.

AVOID SYNTHETIC TELLS (HIGH PRIORITY)
- Avoid repetitive turn patterns (e.g., every advisor turn ending the same way).
- Avoid abrupt topic jumps; add light connective tissue between sections.
- Avoid overly tidy, exhaustive lists; prefer recall-in-pieces + occasional "oh, also…".
- Avoid over-confident precision when humans would be unsure (but never change any grounded numbers).

ANTI "OVER-COACHING" / REAL-WORLD DOSAGE (HIGH PRIORITY)
- Reduce "perfect technique" density.
  If the transcript currently has long loops of reframing/probing/assumption-checking around a single numeric item, compress it.
  Keep most numeric topics to: ask → answer → quick clarification (optional) → move on.
- Allow occasional pragmatic client pushback when the conversation gets stuck.
  Example vibe (do not copy literally): "Can we just put it down as about 2.5k and keep going?"
  The advisor should accept and proceed.

REALISTIC RESPONSE LATENCY (IMPORTANT)
- If the advisor is about to restate a precise number (especially a total), add a tiny beat first (1 line max):
  "One sec—I'm writing that down" / "Hang on" / "Let me make sure I heard you right".
  This should not add new facts; it's just pacing.

ANTI "TRAINING SCRIPT" CONSTRAINTS (HIGH PRIORITY)
- Do NOT add repeated "quick recap / restate-and-confirm" blocks after every section.
  Keep recaps rare and short (ideally one near the end).
- Do NOT add process narration like "for the record", "my worksheet", "the software asks", "on our side".
- Avoid repeating the same small-talk bridge line multiple times (e.g. don't keep re-opening with "before we jump in...").

STYLE
- Natural spoken English.
- Keep most turns short, but allow occasional longer advisor summaries.
- Avoid sounding too polished; slight messiness is good.
- Avoid repetitive filler and avoid making every turn equally long.

OUTPUT LENGTH
- Target expansion: +15% to +40% more lines than the skeleton.
- Prefer quality (natural pacing) over sheer length.

INPUTS
- household_type: {{household_type}}
- client1_name: {{client1_name}}
- client2_name: {{client2_name}}
- skeleton_transcript (verbatim):
{{skeleton_transcript}}

OPENING / CLOSING (REQUIRED)
- Ensure the finished transcript begins with a natural greeting + quick advisor intro + invitation to speak ("tell me about you") using the client name(s) in-text.
- Ensure the finished transcript ends with a brief wrap-up and mutual goodbyes:
  - Advisor says thanks/next steps and goodbye
  - Each client says thanks/bye

OUTPUT
- Return only the finalized transcript.
