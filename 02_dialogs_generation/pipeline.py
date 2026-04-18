from __future__ import annotations

import json
import logging
import os
from dataclasses import asdict
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

from config import GenerationConfig, Paths, default_repo_root
from examples import load_example_transcripts
from profile_digest import build_profile_digest, extract_record_ids
from io_utils import iter_json_objects, load_json, save_json, save_text
from openai_client import OpenAIResponsesClient
from prompt_loader import load_prompts, render_prompt
from scenario import sample_scenario
from schemas import (
    ConversationOutline,
    HouseholdType,
    Personas,
    PhaseGenerationResult,
    StateUpdateResult,
)
from state import ConversationState, default_state


logger = logging.getLogger(__name__)


def _household_type(financial_profile: Dict[str, Any]) -> HouseholdType:
    hh = financial_profile.get("households") or {}
    # Prefer explicit schema field if present.
    if isinstance(hh.get("num_adults"), (int, float)):
        return "couple" if int(hh["num_adults"]) >= 2 else "single"

    people = financial_profile.get("people") or []
    return "couple" if len(people) >= 2 else "single"


def _speaker_labels(hh_type: HouseholdType) -> Tuple[str, Optional[str]]:
    if hh_type == "couple":
        return "Client 1:", "Client 2:"
    return "Client:", None


def _format_profile_for_prompt(profile: Dict[str, Any]) -> str:
    return json.dumps(profile, ensure_ascii=False, indent=2)


def _count_turns(lines: List[str]) -> int:
    return sum(1 for l in lines if l.strip())


class DialogGenerationPipeline:
    def __init__(self, *, repo_root: Optional[Path] = None) -> None:
        self.repo_root = repo_root or default_repo_root()
        self.paths = Paths(repo_root=self.repo_root)
        self.prompts = load_prompts(self.paths.prompt_dir)

    def run(self, cfg: GenerationConfig) -> None:
        cfg.output_dir.mkdir(parents=True, exist_ok=True)
        logging.basicConfig(
            level=logging.INFO,
            format="%(asctime)s | %(levelname)s | %(message)s",
        )

        priors = load_json(cfg.priors_path)

        examples_mode = str(os.getenv("EXAMPLE_TRANSCRIPTS_MODE", "excerpt")).strip().lower()
        if examples_mode not in {"excerpt", "full", "none"}:
            examples_mode = "excerpt"
        example_transcripts = load_example_transcripts(repo_root=self.repo_root, mode=examples_mode)  # type: ignore[arg-type]

        rng = np.random.default_rng(int(cfg.seed))
        llm = OpenAIResponsesClient(
            model=cfg.model.model,
            temperature=cfg.model.temperature,
            max_output_tokens=cfg.model.max_output_tokens,
            seed=cfg.model.seed,
        )

        profiles = list(iter_json_objects(cfg.financial_dataset_json_path))
        if not profiles:
            raise ValueError(f"No financial profiles found in {cfg.financial_dataset_json_path}")

        n = min(int(cfg.n), len(profiles))
        logger.info("Generating %s transcripts", n)

        for idx in range(n):
            profile = profiles[idx]
            hh_id = str(profile.get("household_id") or profile.get("households", {}).get("household_id") or idx)
            dialog_id = f"DIALOG_{hh_id}"
            scenario_name = sample_scenario(priors, rng)

            digest = build_profile_digest(profile)
            record_ids = extract_record_ids(profile)
            valid_ids_json = json.dumps(
                {
                    "household_id": record_ids.household_id,
                    "person_ids": record_ids.person_ids,
                    "income_line_ids": record_ids.income_line_ids,
                    "asset_ids": record_ids.asset_ids,
                    "liability_ids": record_ids.liability_ids,
                    "policy_ids": record_ids.policy_ids,
                },
                ensure_ascii=False,
                indent=2,
            )

            hh_type = _household_type(profile)
            client1_label, client2_label = _speaker_labels(hh_type)

            logger.info("%s | scenario=%s | household_type=%s", dialog_id, scenario_name, hh_type)

            system_prompt = self.prompts.system

            # 1) Personas
            persona_user = render_prompt(
                self.prompts.persona_generation,
                {
                    "scenario_name": scenario_name,
                    "household_type": hh_type,
                    "financial_profile_json": _format_profile_for_prompt(profile),
                    "financial_profile_digest": digest,
                },
            )
            personas_obj = llm.create_json(system_prompt=system_prompt, user_prompt=persona_user, schema=Personas)
            personas: List[Dict[str, Any]] = [p.model_dump() for p in personas_obj.root]

            # 2) Outline
            outline_user = render_prompt(
                self.prompts.outline,
                {
                    "scenario_name": scenario_name,
                    "household_type": hh_type,
                    "min_turns": str(cfg.min_turns),
                    "max_turns": str(cfg.max_turns),
                    "personas_json": json.dumps(personas, ensure_ascii=False, indent=2),
                    "financial_profile_json": _format_profile_for_prompt(profile),
                    "financial_profile_digest": digest,
                    "valid_record_ids_json": valid_ids_json,
                },
            )
            outline = llm.create_json(
                system_prompt=system_prompt,
                user_prompt=outline_user,
                schema=ConversationOutline,
            )

            # 3) Phase generation + state updates
            state = default_state()
            transcript_lines: List[str] = []
            phases_out: List[Dict[str, Any]] = []

            used_person_ids: set[str] = set()
            used_income_line_ids: set[str] = set()
            used_asset_ids: set[str] = set()
            used_liability_ids: set[str] = set()
            used_policy_ids: set[str] = set()

            for phase_idx, phase in enumerate(outline.phases):
                if _count_turns(transcript_lines) >= cfg.max_turns:
                    break

                phase_user = render_prompt(
                    self.prompts.phase_generation,
                    {
                        "scenario_name": scenario_name,
                        "household_type": hh_type,
                        "phase_index": str(phase_idx + 1),
                        "phase_name": phase.phase_name,
                        "phase_json": json.dumps(phase.model_dump(), ensure_ascii=False, indent=2),
                        "outline_json": json.dumps(outline.model_dump(), ensure_ascii=False, indent=2),
                        "personas_json": json.dumps(personas, ensure_ascii=False, indent=2),
                        "state_json": json.dumps(state.to_dict(), ensure_ascii=False, indent=2),
                        "transcript_so_far": "\n".join(transcript_lines[-200:]),
                        "client1_label": client1_label,
                        "client2_label": client2_label or "Client 2:",
                        "example_transcripts": example_transcripts,
                        "financial_profile_digest": digest,
                        "valid_record_ids_json": valid_ids_json,
                    },
                )
                phase_res = llm.create_json(
                    system_prompt=system_prompt,
                    user_prompt=phase_user,
                    schema=PhaseGenerationResult,
                )

                # Coverage tracking (model provides record ids it referenced)
                used_person_ids.update([i for i in phase_res.phase_notes.used_person_ids if i in record_ids.person_ids])
                used_income_line_ids.update(
                    [i for i in phase_res.phase_notes.used_income_line_ids if i in record_ids.income_line_ids]
                )
                used_asset_ids.update([i for i in phase_res.phase_notes.used_asset_ids if i in record_ids.asset_ids])
                used_liability_ids.update(
                    [i for i in phase_res.phase_notes.used_liability_ids if i in record_ids.liability_ids]
                )
                used_policy_ids.update([i for i in phase_res.phase_notes.used_policy_ids if i in record_ids.policy_ids])

                new_lines = [l.strip() for l in phase_res.utterances if str(l).strip()]
                transcript_lines.extend(new_lines)

                # State update
                state_user = render_prompt(
                    self.prompts.state_update,
                    {
                        "scenario_name": scenario_name,
                        "household_type": hh_type,
                        "phase_index": str(phase_idx + 1),
                        "phase_name": phase.phase_name,
                        "personas_json": json.dumps(personas, ensure_ascii=False, indent=2),
                        "financial_profile_digest": digest,
                        "previous_state_json": json.dumps(state.to_dict(), ensure_ascii=False, indent=2),
                        "new_utterances": "\n".join(new_lines),
                    },
                )
                state_res = llm.create_json(
                    system_prompt=system_prompt,
                    user_prompt=state_user,
                    schema=StateUpdateResult,
                )

                state = ConversationState(**state_res.state.model_dump())

                phases_out.append(
                    {
                        "phase_index": phase_idx + 1,
                        "phase_name": phase.phase_name,
                        "phase_plan": phase.model_dump(),
                        "utterances": new_lines,
                        "phase_notes": phase_res.phase_notes.model_dump(),
                        "state_after": state.to_dict(),
                        "phase_summary": state_res.phase_summary,
                    }
                )

            # If any records were missed, run one extra close-out phase to cover gaps.
            remaining_income = [i for i in record_ids.income_line_ids if i not in used_income_line_ids]
            remaining_assets = [i for i in record_ids.asset_ids if i not in used_asset_ids]
            remaining_liabs = [i for i in record_ids.liability_ids if i not in used_liability_ids]
            remaining_policies = [i for i in record_ids.policy_ids if i not in used_policy_ids]

            has_gaps = bool(remaining_income or remaining_assets or remaining_liabs or remaining_policies)
            if has_gaps and _count_turns(transcript_lines) < cfg.max_turns:
                gap_phase = {
                    "phase_name": "Coverage close-out (fill missing records)",
                    "objectives": [
                        "Make sure all remaining income lines/assets/liabilities/policies are explicitly discussed",
                        "Have the advisor summarize and confirm understanding",
                    ],
                    "must_cover_topics": [
                        "Remaining record IDs",
                        "Confirm amounts as ranges/rounded",
                        "Next steps",
                    ],
                    "target_turns": min(120, max(30, int(cfg.max_turns - _count_turns(transcript_lines)))),
                    "realism_hooks": [
                        "Advisor notices they forgot to confirm a few items",
                        "Client corrects one small detail",
                    ],
                    "remaining_record_ids": {
                        "income_line_ids": remaining_income,
                        "asset_ids": remaining_assets,
                        "liability_ids": remaining_liabs,
                        "policy_ids": remaining_policies,
                    },
                }

                phase_user = render_prompt(
                    self.prompts.phase_generation,
                    {
                        "scenario_name": scenario_name,
                        "household_type": hh_type,
                        "phase_index": str(len(phases_out) + 1),
                        "phase_name": str(gap_phase["phase_name"]),
                        "phase_json": json.dumps(gap_phase, ensure_ascii=False, indent=2),
                        "outline_json": json.dumps(outline.model_dump(), ensure_ascii=False, indent=2),
                        "personas_json": json.dumps(personas, ensure_ascii=False, indent=2),
                        "state_json": json.dumps(state.to_dict(), ensure_ascii=False, indent=2),
                        "transcript_so_far": "\n".join(transcript_lines[-200:]),
                        "client1_label": client1_label,
                        "client2_label": client2_label or "Client 2:",
                        "example_transcripts": example_transcripts,
                        "financial_profile_digest": digest,
                        "valid_record_ids_json": valid_ids_json,
                    },
                )
                phase_res = llm.create_json(
                    system_prompt=system_prompt,
                    user_prompt=phase_user,
                    schema=PhaseGenerationResult,
                )
                new_lines = [l.strip() for l in phase_res.utterances if str(l).strip()]
                transcript_lines.extend(new_lines)
                phases_out.append(
                    {
                        "phase_index": len(phases_out) + 1,
                        "phase_name": gap_phase["phase_name"],
                        "phase_plan": gap_phase,
                        "utterances": new_lines,
                        "phase_notes": phase_res.phase_notes.model_dump(),
                        "state_after": state.to_dict(),
                        "phase_summary": "Auto-generated close-out phase to cover remaining records.",
                    }
                )

            transcript_text = "\n".join(transcript_lines).strip() + "\n"
            out_obj = {
                "id": dialog_id,
                "scenario": scenario_name,
                "financial_profile": profile,
                "personas": personas,
                "transcript": transcript_text,
                "phases": phases_out,
                "metadata": {
                    "num_turns": _count_turns(transcript_lines),
                    "household_type": hh_type,
                    "scenario_name": scenario_name,
                },
            }

            out_json_path = cfg.output_dir / f"{dialog_id}.json"
            save_json(out_json_path, out_obj)
            if cfg.save_txt:
                save_text(cfg.output_dir / f"{dialog_id}.txt", transcript_text)

            logger.info("Wrote %s (turns=%s)", out_json_path.name, out_obj["metadata"]["num_turns"])
