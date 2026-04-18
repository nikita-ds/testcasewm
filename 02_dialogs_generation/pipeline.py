from __future__ import annotations

import json
import logging
import os
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
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


def _norm_ids(values: List[Any]) -> List[str]:
    out: List[str] = []
    for v in values or []:
        s = str(v).strip()
        if s:
            out.append(s)
    return out


def _validate_phase_used_ids(*, dialog_id: str, phase_name: str, phase_idx: int, record_ids: Any, phase_notes: Any) -> None:
    allowed_people = set(_norm_ids(getattr(record_ids, "person_ids", [])))
    allowed_income = set(_norm_ids(getattr(record_ids, "income_line_ids", [])))
    allowed_assets = set(_norm_ids(getattr(record_ids, "asset_ids", [])))
    allowed_liabs = set(_norm_ids(getattr(record_ids, "liability_ids", [])))
    allowed_policies = set(_norm_ids(getattr(record_ids, "policy_ids", [])))

    used_people = _norm_ids(getattr(phase_notes, "used_person_ids", []))
    used_income = _norm_ids(getattr(phase_notes, "used_income_line_ids", []))
    used_assets = _norm_ids(getattr(phase_notes, "used_asset_ids", []))
    used_liabs = _norm_ids(getattr(phase_notes, "used_liability_ids", []))
    used_policies = _norm_ids(getattr(phase_notes, "used_policy_ids", []))

    invalid: Dict[str, List[str]] = {}
    inv_people = sorted({i for i in used_people if i not in allowed_people})
    inv_income = sorted({i for i in used_income if i not in allowed_income})
    inv_assets = sorted({i for i in used_assets if i not in allowed_assets})
    inv_liabs = sorted({i for i in used_liabs if i not in allowed_liabs})
    inv_policies = sorted({i for i in used_policies if i not in allowed_policies})
    if inv_people:
        invalid["used_person_ids"] = inv_people
    if inv_income:
        invalid["used_income_line_ids"] = inv_income
    if inv_assets:
        invalid["used_asset_ids"] = inv_assets
    if inv_liabs:
        invalid["used_liability_ids"] = inv_liabs
    if inv_policies:
        invalid["used_policy_ids"] = inv_policies

    if invalid:
        raise ValueError(
            "Invalid record IDs returned by model "
            f"({dialog_id} phase={phase_idx} name={phase_name}): {json.dumps(invalid, ensure_ascii=False)}"
        )


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


def _normalize_misunderstood_terms(values: Any) -> List[str]:
    out: List[str] = []
    for v in values or []:
        if isinstance(v, str):
            s = v.strip()
            if s:
                out.append(s)
            continue
        if isinstance(v, dict):
            term = str(v.get("term") or "").strip()
            if term:
                out.append(term)
            continue
        term = getattr(v, "term", None)
        if term is not None:
            s = str(term).strip()
            if s:
                out.append(s)
    return out


class DialogGenerationPipeline:
    def __init__(self, *, repo_root: Optional[Path] = None) -> None:
        self.repo_root = repo_root or default_repo_root()
        self.paths = Paths(repo_root=self.repo_root)
        self.prompts = load_prompts(self.paths.prompt_dir)

    def _dialog_seed(self, *, base_seed: int, idx: int, household_id: str) -> int:
        # Stable-ish deterministic seed per dialog; avoids shared RNG in parallel mode.
        # (We still keep ordering deterministic for the first N profiles.)
        return int((base_seed * 1_000_003 + idx * 9_973 + (hash(household_id) & 0xFFFF_FFFF)) % (2**31 - 1))

    def _generate_one(
        self,
        *,
        cfg: GenerationConfig,
        priors: Dict[str, Any],
        example_transcripts: str,
        profile: Dict[str, Any],
        idx: int,
    ) -> str:
        hh_id = str(profile.get("household_id") or profile.get("households", {}).get("household_id") or idx)
        dialog_id = f"DIALOG_{hh_id}"

        dialog_seed = self._dialog_seed(base_seed=int(cfg.seed), idx=idx, household_id=hh_id)
        rng = np.random.default_rng(int(dialog_seed))

        # Use a per-dialog LLM client; safer for threads and enables per-dialog OpenAI seed offsets.
        openai_seed = cfg.model.seed
        if openai_seed is not None:
            openai_seed = int(openai_seed) + int(idx)
        llm = OpenAIResponsesClient(
            model=cfg.model.model,
            temperature=cfg.model.temperature,
            max_output_tokens=cfg.model.max_output_tokens,
            seed=openai_seed,
        )

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

        logger.info("%s | scenario=%s | household_type=%s | seed=%s", dialog_id, scenario_name, hh_type, dialog_seed)
        system_prompt = self.prompts.system

        t0 = time.perf_counter()

        # 1) Personas
        logger.info("%s | step=personas | start", dialog_id)
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
        logger.info("%s | step=personas | done | dt=%.2fs", dialog_id, time.perf_counter() - t0)

        # 2) Outline
        t1 = time.perf_counter()
        logger.info("%s | step=outline | start", dialog_id)
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
        logger.info(
            "%s | step=outline | done | phases=%s | target_turns=%s | dt=%.2fs",
            dialog_id,
            len(outline.phases),
            getattr(outline, "total_target_turns", None),
            time.perf_counter() - t1,
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
                logger.info("%s | max_turns reached before phase %s", dialog_id, phase_idx + 1)
                break

            logger.info(
                "%s | phase=%s/%s | name=%s | start",
                dialog_id,
                phase_idx + 1,
                len(outline.phases),
                phase.phase_name,
            )
            tp = time.perf_counter()
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

            _validate_phase_used_ids(
                dialog_id=dialog_id,
                phase_name=phase.phase_name,
                phase_idx=phase_idx + 1,
                record_ids=record_ids,
                phase_notes=phase_res.phase_notes,
            )

            used_person_ids.update([i for i in _norm_ids(phase_res.phase_notes.used_person_ids) if i in record_ids.person_ids])
            used_income_line_ids.update(
                [i for i in _norm_ids(phase_res.phase_notes.used_income_line_ids) if i in record_ids.income_line_ids]
            )
            used_asset_ids.update([i for i in _norm_ids(phase_res.phase_notes.used_asset_ids) if i in record_ids.asset_ids])
            used_liability_ids.update(
                [i for i in _norm_ids(phase_res.phase_notes.used_liability_ids) if i in record_ids.liability_ids]
            )
            used_policy_ids.update(
                [i for i in _norm_ids(phase_res.phase_notes.used_policy_ids) if i in record_ids.policy_ids]
            )

            new_lines = [l.strip() for l in phase_res.utterances if str(l).strip()]
            transcript_lines.extend(new_lines)

            # State update
            ts = time.perf_counter()
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

            state_dict = state_res.state.model_dump()
            state_dict["misunderstood_terms"] = _normalize_misunderstood_terms(state_dict.get("misunderstood_terms"))
            state = ConversationState(**state_dict)

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
            logger.info(
                "%s | phase=%s/%s | done | turns=+%s total=%s | dt_phase=%.2fs dt_state=%.2fs",
                dialog_id,
                phase_idx + 1,
                len(outline.phases),
                len(new_lines),
                _count_turns(transcript_lines),
                time.perf_counter() - tp,
                time.perf_counter() - ts,
            )

        # If any records were missed, run 1-3 close-out phases to cover gaps.
        close_out_count = 0
        while close_out_count < 3 and _count_turns(transcript_lines) < cfg.max_turns:
            remaining_people = [i for i in record_ids.person_ids if i not in used_person_ids]
            remaining_income = [i for i in record_ids.income_line_ids if i not in used_income_line_ids]
            remaining_assets = [i for i in record_ids.asset_ids if i not in used_asset_ids]
            remaining_liabs = [i for i in record_ids.liability_ids if i not in used_liability_ids]
            remaining_policies = [i for i in record_ids.policy_ids if i not in used_policy_ids]

            has_gaps = bool(remaining_people or remaining_income or remaining_assets or remaining_liabs or remaining_policies)
            if not has_gaps:
                break

            logger.info(
                "%s | close_out=%s | remaining: people=%s income=%s assets=%s liabs=%s policies=%s",
                dialog_id,
                close_out_count + 1,
                len(remaining_people),
                len(remaining_income),
                len(remaining_assets),
                len(remaining_liabs),
                len(remaining_policies),
            )

            remaining_turn_budget = int(cfg.max_turns - _count_turns(transcript_lines))
            if remaining_turn_budget <= 0:
                break

            gap_phase = {
                "phase_name": "Coverage close-out (fill missing records)",
                "objectives": [
                    "Make sure all remaining PEOPLE / income lines / assets / liabilities / policies are explicitly discussed",
                    "Have the advisor summarize and confirm understanding",
                ],
                "must_cover_topics": [
                    "Remaining record IDs (phase_notes only)",
                    "Confirm amounts as ranges/rounded",
                    "Next steps",
                ],
                "target_turns": min(300, max(60, remaining_turn_budget)),
                "realism_hooks": [
                    "Advisor notices they forgot to confirm a few items",
                    "Client corrects one small detail",
                ],
                "remaining_record_ids": {
                    "person_ids": remaining_people,
                    "income_line_ids": remaining_income,
                    "asset_ids": remaining_assets,
                    "liability_ids": remaining_liabs,
                    "policy_ids": remaining_policies,
                },
            }

            phase_index = len(phases_out) + 1
            tp = time.perf_counter()
            phase_user = render_prompt(
                self.prompts.phase_generation,
                {
                    "scenario_name": scenario_name,
                    "household_type": hh_type,
                    "phase_index": str(phase_index),
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

            _validate_phase_used_ids(
                dialog_id=dialog_id,
                phase_name=str(gap_phase["phase_name"]),
                phase_idx=phase_index,
                record_ids=record_ids,
                phase_notes=phase_res.phase_notes,
            )

            used_person_ids.update([i for i in _norm_ids(phase_res.phase_notes.used_person_ids) if i in record_ids.person_ids])
            used_income_line_ids.update(
                [i for i in _norm_ids(phase_res.phase_notes.used_income_line_ids) if i in record_ids.income_line_ids]
            )
            used_asset_ids.update([i for i in _norm_ids(phase_res.phase_notes.used_asset_ids) if i in record_ids.asset_ids])
            used_liability_ids.update(
                [i for i in _norm_ids(phase_res.phase_notes.used_liability_ids) if i in record_ids.liability_ids]
            )
            used_policy_ids.update(
                [i for i in _norm_ids(phase_res.phase_notes.used_policy_ids) if i in record_ids.policy_ids]
            )

            new_lines = [l.strip() for l in phase_res.utterances if str(l).strip()]
            transcript_lines.extend(new_lines)

            state_user = render_prompt(
                self.prompts.state_update,
                {
                    "scenario_name": scenario_name,
                    "household_type": hh_type,
                    "phase_index": str(phase_index),
                    "phase_name": str(gap_phase["phase_name"]),
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
            state_dict = state_res.state.model_dump()
            state_dict["misunderstood_terms"] = _normalize_misunderstood_terms(state_dict.get("misunderstood_terms"))
            state = ConversationState(**state_dict)

            phases_out.append(
                {
                    "phase_index": phase_index,
                    "phase_name": gap_phase["phase_name"],
                    "phase_plan": gap_phase,
                    "utterances": new_lines,
                    "phase_notes": phase_res.phase_notes.model_dump(),
                    "state_after": state.to_dict(),
                    "phase_summary": state_res.phase_summary,
                }
            )
            logger.info(
                "%s | close_out=%s | done | turns=+%s total=%s | dt=%.2fs",
                dialog_id,
                close_out_count + 1,
                len(new_lines),
                _count_turns(transcript_lines),
                time.perf_counter() - tp,
            )
            close_out_count += 1

        # Final hard check for coverage.
        remaining_people = [i for i in record_ids.person_ids if i not in used_person_ids]
        remaining_income = [i for i in record_ids.income_line_ids if i not in used_income_line_ids]
        remaining_assets = [i for i in record_ids.asset_ids if i not in used_asset_ids]
        remaining_liabs = [i for i in record_ids.liability_ids if i not in used_liability_ids]
        remaining_policies = [i for i in record_ids.policy_ids if i not in used_policy_ids]
        if remaining_people or remaining_income or remaining_assets or remaining_liabs or remaining_policies:
            remaining_by_type = {
                "person_ids": remaining_people,
                "income_line_ids": remaining_income,
                "asset_ids": remaining_assets,
                "liability_ids": remaining_liabs,
                "policy_ids": remaining_policies,
            }
            raise ValueError(
                "Coverage incomplete after close-out phases "
                f"({dialog_id}): {json.dumps(remaining_by_type, ensure_ascii=False)}"
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
                "dialog_seed": dialog_seed,
                "openai_seed": openai_seed,
            },
        }

        out_json_path = cfg.output_dir / f"{dialog_id}.json"
        save_json(out_json_path, out_obj)
        if cfg.save_txt:
            save_text(cfg.output_dir / f"{dialog_id}.txt", transcript_text)

        logger.info(
            "%s | wrote=%s | turns=%s | total_dt=%.2fs",
            dialog_id,
            out_json_path.name,
            out_obj["metadata"]["num_turns"],
            time.perf_counter() - t0,
        )
        return dialog_id

    def run(self, cfg: GenerationConfig) -> None:
        cfg.output_dir.mkdir(parents=True, exist_ok=True)
        logging.basicConfig(
            level=logging.INFO,
            format="%(asctime)s | %(levelname)s | %(threadName)s | %(message)s",
        )

        priors = load_json(cfg.priors_path)

        examples_mode = str(os.getenv("EXAMPLE_TRANSCRIPTS_MODE", "excerpt")).strip().lower()
        if examples_mode not in {"excerpt", "full", "none"}:
            examples_mode = "excerpt"
        example_transcripts = load_example_transcripts(repo_root=self.repo_root, mode=examples_mode)  # type: ignore[arg-type]

        profiles = list(iter_json_objects(cfg.financial_dataset_json_path))
        if not profiles:
            raise ValueError(f"No financial profiles found in {cfg.financial_dataset_json_path}")

        n = min(int(cfg.n), len(profiles))
        logger.info("Generating %s transcripts", n)

        profiles = profiles[:n]
        workers = max(1, int(getattr(cfg, "workers", 1) or 1))
        if workers == 1 or n <= 1:
            for idx, profile in enumerate(profiles):
                self._generate_one(cfg=cfg, priors=priors, example_transcripts=example_transcripts, profile=profile, idx=idx)
            return

        logger.info("Generating %s transcripts with workers=%s", n, workers)
        with ThreadPoolExecutor(max_workers=workers, thread_name_prefix="dialog") as ex:
            futures = [
                ex.submit(
                    self._generate_one,
                    cfg=cfg,
                    priors=priors,
                    example_transcripts=example_transcripts,
                    profile=profile,
                    idx=idx,
                )
                for idx, profile in enumerate(profiles)
            ]
            for fut in as_completed(futures):
                dialog_id = fut.result()
                logger.info("done: %s", dialog_id)
