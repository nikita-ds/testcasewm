You will FINALIZE a transcript skeleton into a much more realistic advisor-client conversation.

GOAL
- Make the dialogue feel close to a real discovery / fact-find meeting, not like stitched chunks.
- Expand the conversation noticeably while preserving all grounded facts already present in the skeleton.
- Increase realism through hesitation, uncertainty, partial recall, small corrections, and natural follow-up questions.

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
- Do NOT ask for or mention any PII: Social Security numbers, full addresses, account numbers, passwords, emails, phone numbers.

NAME USAGE (IMPORTANT)
- Use the provided client name(s) inside the utterance text for natural addressing.
- Do NOT change the speaker prefixes.

FACT PRESERVATION RULES (STRICT)
- Do not invent new accounts, policies, debts, dates, family members, employers, or numeric facts.
- Do not change the meaning of existing numbers.
- If the skeleton gives a total expense number, you may unpack how the client remembers it into separate categories only if the categories are explicitly framed as a recall process and still consistent with the known totals.
- Do not remove required factual lines; you may rewrite them into more natural speech while preserving meaning.

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
- Small talk often pops up during admin moments (FACT-SAFE): weather, holidays, scheduling, generic weekend plans.
- Mild pushback and repair is normal: a client challenges, advisor reassures, then returns to the agenda.

LIGHT SMALL-TALK (SAFE "WATER")
- Add 2–5 brief human moments across the transcript: weather, commute/traffic, scheduling, generic weekend plans.
- If you include hobbies, do it as a generic question + vague answer (no specific hobby facts) unless the skeleton already mentions a specific hobby.
- Keep these moments short (1–3 turns each) and naturally return to the agenda.

AVOID SYNTHETIC TELLS (HIGH PRIORITY)
- Avoid repetitive turn patterns (e.g., every advisor turn ending the same way).
- Avoid abrupt topic jumps; add light connective tissue between sections.
- Avoid overly tidy, exhaustive lists; prefer recall-in-pieces + occasional "oh, also…".
- Avoid over-confident precision when humans would be unsure (but never change any grounded numbers).

STYLE
- Natural spoken English.
- Keep most turns short, but allow occasional longer advisor summaries.
- Avoid sounding too polished; slight messiness is good.
- Avoid repetitive filler and avoid making every turn equally long.

OUTPUT LENGTH
- Target expansion: +35% to +80% more lines than the skeleton.
- The finished dialogue should feel materially richer than the skeleton.

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
