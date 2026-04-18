You are evaluating whether a candidate advisor-client financial dialogue reads like a real human conversation.

TASK
- Judge the CANDIDATE excerpts.
- Compare them against NEGATIVE CONTROLS, which are known synthetic dialogues.
- Focus on realism of conversational flow, memory behavior, numeric recall style, repairs, uncertainty, and whether the transcript feels naturally spoken rather than mechanically generated.

IMPORTANT
- The negative controls are NOT full dialogs. They are random excerpts from known synthetic transcripts.
- The candidate may still be synthetic. You are estimating whether it would plausibly be mistaken for a real transcript by a careful reviewer.
- Do not reward generic polish alone. Realistic messiness is often a positive signal.

WHAT TO LOOK FOR
- Natural uncertainty: approximate recall, partial memory, self-correction, hesitation.
- Granular remembering of expenses instead of only neat totals.
- Human evaluative language about magnitudes.
- Organic turn-taking and interruptions.
- Whether transitions feel stitched or whether they flow like one meeting.
- Synthetic tells: unnatural repetition, abrupt topic jumps, robotic summaries, over-tidy patterns, or implausible rhythm.

INPUTS
- dialog_id: {{dialog_id}}
- scenario_name: {{scenario_name}}
- household_type: {{household_type}}

- candidate_excerpts_json:
{{candidate_excerpts_json}}

- candidate_skeleton_excerpts_json:
{{candidate_skeleton_excerpts_json}}

- negative_controls_json:
{{negative_controls_json}}

OUTPUT (STRICT)
- Return exactly ONE integer number from 1 to 5 (inclusive).
- Output MUST contain only the number and nothing else (no JSON, no words, no punctuation).

SCORE MEANING
- 1 = extremely synthetic / obviously generated.
- 3 = unclear / mixed signals.
- 5 = extremely realistic / could plausibly be mistaken for a real transcript.

CALIBRATION
- Be conservative.
- Use 5 only when the candidate clearly looks more human than the negative controls.
- Do NOT default to a "safe" constant score. Scores should vary across candidates.
- If you arrive at 3 (uncertain), do a quick second pass: decide whether 2 or 4 is a better fit. Use 3 ONLY if positives and negatives are truly balanced.
