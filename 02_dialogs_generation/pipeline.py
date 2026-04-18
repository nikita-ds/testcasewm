from __future__ import annotations

import json
import hashlib
import logging
import os
import time
import csv
import threading
import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

import numpy as np

from config import GenerationConfig, Paths, default_repo_root
from deepseek_client import DeepSeekChatClient
from examples import load_example_transcripts
from profile_digest import build_profile_digest, extract_record_ids
from io_utils import iter_json_objects, load_json, save_json, save_text
from openai_client import OpenAIResponsesClient
from prompt_loader import load_prompts, render_prompt
from scenario import sample_scenario
from money_rounding import is_money_field_path, round_money_in_obj, round_money_value
from normalization import is_state_like_field, state_variants
from schemas import (
    ConversationOutline,
    HouseholdType,
    Personas,
    PhaseGenerationResult,
    StateUpdateResult,
    EvidenceExtractionBatchResult,
    FieldChunkGenerationResult,
    TranscriptRealismJudgeResult,
)
from state import ConversationState, default_state


logger = logging.getLogger(__name__)

_VALIDATION_REPORT_LOCK = threading.Lock()
_REGISTRY_LOCK = threading.Lock()


def _append_validation_failure_csv(
    *,
    out_dir: Path,
    row: Dict[str, Any],
    filename: str = "validation_failures.csv",
) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / filename

    # Intentionally minimal schema (per user request): only the household and the failing field paths.
    fieldnames = ["household_id", "failed_field_paths"]

    safe_row: Dict[str, str] = {k: "" for k in fieldnames}
    for k in fieldnames:
        v = row.get(k)
        if v is None:
            safe_row[k] = ""
        elif isinstance(v, (list, dict)):
            safe_row[k] = json.dumps(v, ensure_ascii=False)
        else:
            safe_row[k] = str(v)

    def _read_existing_header() -> Optional[List[str]]:
        try:
            if (not path.exists()) or (path.stat().st_size == 0):
                return None
            with path.open("r", encoding="utf-8", newline="") as f:
                r = csv.reader(f)
                return next(r, None)
        except Exception:
            return None

    with _VALIDATION_REPORT_LOCK:
        existing_header = _read_existing_header()
        if existing_header and existing_header != fieldnames:
            rotated = out_dir / "validation_failures_full.csv"
            try:
                if not rotated.exists():
                    path.rename(rotated)
                else:
                    # Avoid overwriting: keep the current file and write minimal report to a fresh file.
                    pass
            except Exception:
                # If rotation fails, continue appending; caller still has JSON artifacts for debugging.
                pass

        # Re-evaluate in case rotation succeeded.
        write_header = (not path.exists()) or (path.stat().st_size == 0)
        with path.open("a", encoding="utf-8", newline="") as f:
            w = csv.DictWriter(f, fieldnames=fieldnames)
            if write_header:
                w.writeheader()
            w.writerow(safe_row)


def _profile_household_id(profile: Dict[str, Any]) -> str:
    return str(profile.get("household_id") or (profile.get("households") or {}).get("household_id") or "")


def _profile_scenario(profile: Dict[str, Any]) -> str:
    return str((profile.get("households") or {}).get("scenario") or profile.get("scenario") or "").strip()


def _profile_income(profile: Dict[str, Any]) -> Optional[float]:
    hh = profile.get("households") or {}
    v = hh.get("annual_household_gross_income")
    try:
        return float(v)
    except Exception:
        return None


def _profile_assets(profile: Dict[str, Any]) -> Optional[float]:
    hh = profile.get("households") or {}
    v = hh.get("investable_assets_total")
    try:
        return float(v)
    except Exception:
        return None


def _quantile_edges(values: List[float], bins: int) -> List[float]:
    if bins <= 1:
        return []
    xs = sorted([float(v) for v in values if v is not None])
    if not xs:
        return []
    n = len(xs)
    edges: List[float] = []
    # bins=3 -> q=1/3,2/3; bins=4 -> q=0.25,0.5,0.75
    for i in range(1, int(bins)):
        q = i / float(bins)
        idx = int(round(q * (n - 1)))
        idx = max(0, min(n - 1, idx))
        edges.append(xs[idx])
    # Ensure non-decreasing unique-ish edges.
    out: List[float] = []
    last = None
    for e in edges:
        if last is None or e > last:
            out.append(e)
            last = e
    return out


def _bucket_index(value: Optional[float], edges: List[float]) -> int:
    if value is None:
        return -1
    v = float(value)
    for i, e in enumerate(edges):
        if v <= float(e):
            return int(i)
    return int(len(edges))


def _load_registry_households(path: Path, *, skip_statuses: Iterable[str]) -> set[str]:
    if not path.exists() or path.stat().st_size == 0:
        return set()
    skip = {str(s).strip().lower() for s in (skip_statuses or []) if str(s).strip()}
    out: set[str] = set()
    try:
        with path.open("r", encoding="utf-8", newline="") as f:
            r = csv.DictReader(f)
            for row in r:
                st = str(row.get("status") or "").strip().lower()
                hh = str(row.get("household_id") or "").strip()
                if hh and (not skip or st in skip):
                    out.add(hh)
    except Exception:
        # If registry is corrupted, don't block generation.
        return set()
    return out


def _load_existing_dialog_households(out_dir: Path) -> set[str]:
    """Return household_ids that already have a generated dialog JSON in out_dir.

    We consider a dialog "existing" if a file named `DIALOG_<household_id>.json` exists.
    (We intentionally ignore auxiliary JSON files like *_metrics.json / *_evidence.json.)
    """

    if out_dir is None or (not out_dir.exists()):
        return set()

    out: set[str] = set()
    try:
        for p in out_dir.glob("DIALOG_*.json"):
            name = p.name
            if name.endswith("_metrics.json") or name.endswith("_evidence.json") or name.endswith("_deepseek_judge.json"):
                continue
            if not name.startswith("DIALOG_"):
                continue
            hh = name[len("DIALOG_") : -len(".json")].strip()
            if hh:
                out.add(hh)
    except Exception:
        return set()
    return out


def _append_registry_row(
    *,
    path: Path,
    row: Dict[str, Any],
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "ts",
        "household_id",
        "dialog_id",
        "status",
        "scenario_name",
        "profile_scenario",
        "mode",
        "error",
    ]
    safe_row: Dict[str, str] = {k: "" for k in fieldnames}
    for k in fieldnames:
        v = row.get(k)
        if v is None:
            safe_row[k] = ""
        else:
            safe_row[k] = str(v)

    with _REGISTRY_LOCK:
        write_header = (not path.exists()) or (path.stat().st_size == 0)
        with path.open("a", encoding="utf-8", newline="") as f:
            w = csv.DictWriter(f, fieldnames=fieldnames)
            if write_header:
                w.writeheader()
            w.writerow(safe_row)


def _select_profiles(
    *,
    profiles: List[Dict[str, Any]],
    n: int,
    seed: int,
    sample_mode: str,
    income_bins: int,
    assets_bins: int,
    output_dir: Optional[Path],
    registry_path: Optional[Path],
    skip_existing: bool,
    registry_skip_statuses: str,
) -> List[Dict[str, Any]]:
    # Filter already-generated households.
    remaining = list(profiles)
    if skip_existing:
        already: set[str] = set()
        if output_dir is not None:
            already |= _load_existing_dialog_households(output_dir)
        if registry_path is not None:
            skip_statuses = [s.strip() for s in str(registry_skip_statuses).split(",") if s.strip()]
            already |= _load_registry_households(registry_path, skip_statuses=skip_statuses)
        if already:
            remaining = [p for p in remaining if _profile_household_id(p) not in already]

    if not remaining:
        return []

    n = min(int(n), len(remaining))
    mode = str(sample_mode or "sequential").strip().lower()
    if mode not in {"sequential", "stratified"}:
        mode = "sequential"
    if mode == "sequential" or n <= 1:
        return remaining[:n]

    # Build buckets from the remaining pool.
    incomes = [v for v in (_profile_income(p) for p in remaining) if v is not None]
    assets = [v for v in (_profile_assets(p) for p in remaining) if v is not None]
    inc_edges = _quantile_edges(incomes, max(1, int(income_bins)))
    ast_edges = _quantile_edges(assets, max(1, int(assets_bins)))

    rng = np.random.default_rng(int(seed))
    strata: Dict[str, List[Dict[str, Any]]] = {}
    for p in remaining:
        sc = _profile_scenario(p) or "(unknown)"
        inc_b = _bucket_index(_profile_income(p), inc_edges)
        ast_b = _bucket_index(_profile_assets(p), ast_edges)
        key = f"{sc}|inc{inc_b}|ast{ast_b}"
        strata.setdefault(key, []).append(p)

    # Shuffle within each stratum deterministically.
    for key, items in strata.items():
        if len(items) > 1:
            perm = rng.permutation(len(items)).tolist()
            strata[key] = [items[i] for i in perm]

    keys = list(strata.keys())
    if len(keys) > 1:
        perm = rng.permutation(len(keys)).tolist()
        keys = [keys[i] for i in perm]

    selected: List[Dict[str, Any]] = []
    # Round-robin over strata.
    while len(selected) < n and keys:
        next_keys: List[str] = []
        for k in keys:
            bucket = strata.get(k) or []
            if bucket:
                selected.append(bucket.pop(0))
                if len(selected) >= n:
                    break
            if strata.get(k):
                next_keys.append(k)
        keys = next_keys

    # Fallback (shouldn't usually happen): top up sequentially.
    if len(selected) < n:
        seen = {_profile_household_id(p) for p in selected}
        for p in remaining:
            if _profile_household_id(p) in seen:
                continue
            selected.append(p)
            if len(selected) >= n:
                break
    return selected


def _chunk_list(items: List[Any], size: int) -> List[List[Any]]:
    if size <= 0:
        return [items]
    out: List[List[Any]] = []
    for i in range(0, len(items), size):
        out.append(items[i : i + size])
    return out


def _batched_targets(
    targets: List[Dict[str, Any]],
    *,
    batch_size: int,
    group_by_record_type: bool,
) -> List[List[Dict[str, Any]]]:
    if not group_by_record_type:
        return _chunk_list(targets, batch_size)

    order = ["households", "people", "income_lines", "assets", "liabilities", "protection_policies"]
    by_type: Dict[str, List[Dict[str, Any]]] = {k: [] for k in order}
    for t in targets:
        rt = str(t.get("record_type") or "")
        if rt in by_type:
            by_type[rt].append(t)
        else:
            # Unknown types go to the end.
            by_type.setdefault(rt, []).append(t)

    batches: List[List[Dict[str, Any]]] = []
    for rt in order + [k for k in by_type.keys() if k not in order]:
        items = by_type.get(rt) or []
        if not items:
            continue
        batches.extend(_chunk_list(items, batch_size))
    return batches


def _build_evidence_targets(
    profile: Dict[str, Any],
    *,
    rng: Optional[np.random.Generator] = None,
    shuffle_within_groups: bool = False,
) -> List[Dict[str, Any]]:
    """Build a deterministic, verifiable list of field targets from the input profile.

    We intentionally keep this list focused on the same columns that appear in the
    profile digest (plus a few household summary fields). This makes downstream
    regex-based checks feasible.
    """

    targets_by_type: Dict[str, List[Dict[str, Any]]] = {
        "households": [],
        "people": [],
        "income_lines": [],
        "assets": [],
        "liabilities": [],
        "protection_policies": [],
    }
    seq = 0

    def _add(*, record_type: str, record_id: Optional[str], field_path: str, source_value: Any) -> None:
        nonlocal seq
        seq += 1
        targets_by_type[record_type].append(
            {
                "target_id": f"t{seq:05d}",
                "record_type": record_type,
                "record_id": record_id,
                "field_path": field_path,
                "source_value": source_value,
            }
        )

    hh = profile.get("households") or {}
    # Households are the first block in field_chunks. Put the most important quantitative
    # aggregates first so the earliest chunk(s) are maximally informative and stable.
    household_fields_core = [
        "annual_household_gross_income",
        "monthly_expenses_total",
        "monthly_debt_cost_total",
        "investable_assets_total",
        "property_value_total",
        "loan_outstanding_total",
        "mortgage_outstanding_total",
        "non_mortgage_outstanding_total",
    ]
    household_fields_tail = [
        "risk_tolerance",
        "tax_bracket_band",
        "residence_state",
        "marital_status",
        "num_adults",
        "num_dependants",
        "scenario",
        "country",
        "market",
    ]
    if shuffle_within_groups and rng is not None and len(household_fields_tail) > 2:
        rng.shuffle(household_fields_tail)
    household_fields = household_fields_core + household_fields_tail
    for k in household_fields:
        if k in hh and hh.get(k) is not None:
            _add(record_type="households", record_id=None, field_path=f"households.{k}", source_value=hh.get(k))

    priority_by_list: Dict[str, List[str]] = {
        # Put quantitative/value fields first for more stable evidence.
        "people": ["gross_annual_income"],
        "income_lines": ["amount_annualized"],
        "assets": ["value"],
        "liabilities": ["outstanding", "monthly_cost"],
        "protection_policies": ["amount_assured", "monthly_cost"],
    }

    def _ordered_keys(list_name: str, keys: List[str]) -> List[str]:
        # Always keep priority keys in front (preserving their relative order);
        # optionally shuffle the remaining tail for less "form-like" chunks.
        prio = [k for k in (priority_by_list.get(list_name) or []) if k in keys]
        rest = [k for k in keys if k not in prio]
        if shuffle_within_groups and rng is not None and len(rest) > 2:
            rng.shuffle(rest)
        return prio + rest

    def _add_rows(list_name: str, id_key: str, field_keys: List[str]) -> None:
        rows = [r for r in (profile.get(list_name) or []) if isinstance(r, dict)]
        # Optional deterministic shuffle of record order (keeps chunks less "form-like").
        if shuffle_within_groups and rng is not None and len(rows) > 1:
            rng.shuffle(rows)
        for r in rows:
            rid = r.get(id_key)
            rid_s = str(rid) if rid is not None else None
            keys = _ordered_keys(list_name, list(field_keys))
            for fk in keys:
                if fk not in r:
                    continue
                val = r.get(fk)
                if val is None:
                    continue
                _add(
                    record_type=list_name,
                    record_id=rid_s,
                    field_path=f"{list_name}[{id_key}={rid_s}].{fk}" if rid_s is not None else f"{list_name}[].{fk}",
                    source_value=val,
                )

    _add_rows(
        "people",
        "person_id",
        ["gross_annual_income", "employment_status", "occupation_group", "role", "client_no", "date_of_birth"],
    )
    _add_rows(
        "income_lines",
        "income_line_id",
        ["amount_annualized", "source_type", "frequency", "owner"],
    )
    _add_rows(
        "assets",
        "asset_id",
        ["value", "asset_type", "subtype", "provider", "provider_type", "owner"],
    )
    _add_rows(
        "liabilities",
        "liability_id",
        ["outstanding", "monthly_cost", "interest_rate", "type", "final_payment_date"],
    )
    _add_rows(
        "protection_policies",
        "policy_id",
        ["amount_assured", "monthly_cost", "policy_type", "assured_until", "owner"],
    )

    # Assemble in coherent topic blocks.
    ordered_types = ["households", "people", "income_lines", "assets", "liabilities", "protection_policies"]
    out: List[Dict[str, Any]] = []
    for rt in ordered_types:
        out.extend(targets_by_type.get(rt) or [])
    return out


def _stringify_value(v: Any) -> str:
    if v is None:
        return ""
    if isinstance(v, bool):
        return "true" if v else "false"
    return str(v)


def _value_variants(v: Any, *, field_path: str = "") -> List[str]:
    """Generate simple string variants for matching in evidence/transcript.

    This is intentionally conservative (regex-free) to keep the validator predictable.
    """

    out: List[str] = []

    if is_state_like_field(field_path):
        out.extend(state_variants(v, _stringify_value))

    s = _stringify_value(v).strip()
    if s:
        out.append(s)

    # Numeric variants: 38198.96 -> 38198.96, 38199, 38,199, $38199, $38,199, 38.2k, $38.2k
    try:
        fv = float(v)
        iv = int(round(fv))
        out.append(str(fv))
        out.append(str(iv))
        out.append(f"{iv:,}")
        out.append(f"${iv}")
        out.append(f"${iv:,}")
        if abs(fv) >= 1000:
            k = fv / 1000.0
            out.append(f"{k:.1f}k")
            out.append(f"${k:.1f}k")
    except Exception:
        pass

    # De-dup while preserving order
    seen: set[str] = set()
    uniq: List[str] = []
    for x in out:
        x2 = str(x).strip()
        if not x2 or x2 in seen:
            continue
        seen.add(x2)
        uniq.append(x2)
    return uniq


def _contains_any(haystack: str, needles: List[str]) -> bool:
    hs = (haystack or "").lower()
    for n in needles:
        if n and str(n).lower() in hs:
            return True
    return False


def _requires_exact_strict_match(field_path: str, value: Any) -> bool:
    if is_money_field_path(field_path):
        return True
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _parse_ymd_date(value: Any) -> Optional[datetime.date]:
    s = str(value or "").strip()
    if not s:
        return None
    try:
        return datetime.date.fromisoformat(s)
    except Exception:
        return None


def _age_on(dob: datetime.date, on_date: datetime.date) -> int:
    # Full years, birthday-aware.
    years = int(on_date.year - dob.year)
    if (on_date.month, on_date.day) < (dob.month, dob.day):
        years -= 1
    return years


def _plausibility_issues_for_profile(profile: Dict[str, Any], *, max_age: int = 100) -> List[Dict[str, Any]]:
    """Return plausibility issues that should force a dialog to fail validation.

    This is intentionally simple and deterministic. It guards against obviously
    implausible future dates (e.g., mortgage payoff or insurance end date when the
    primary is >100 years old).
    """

    people = [p for p in (profile.get("people") or []) if isinstance(p, dict)]
    primary = None
    for p in people:
        if str(p.get("role") or "").strip().lower() == "primary":
            primary = p
            break
    if primary is None and people:
        primary = people[0]

    dob = _parse_ymd_date((primary or {}).get("date_of_birth"))
    if dob is None:
        return []

    issues: List[Dict[str, Any]] = []

    for liab in [x for x in (profile.get("liabilities") or []) if isinstance(x, dict)]:
        dt = _parse_ymd_date(liab.get("final_payment_date"))
        if dt is None:
            continue
        age = _age_on(dob, dt)
        if age > int(max_age):
            issues.append(
                {
                    "field_path": f"liabilities[liability_id={liab.get('liability_id')}].final_payment_date",
                    "value": str(liab.get("final_payment_date")),
                    "age_at_date": age,
                    "max_age": int(max_age),
                }
            )

    for pol in [x for x in (profile.get("protection_policies") or []) if isinstance(x, dict)]:
        dt = _parse_ymd_date(pol.get("assured_until"))
        if dt is None:
            continue
        age = _age_on(dob, dt)
        if age > int(max_age):
            issues.append(
                {
                    "field_path": f"protection_policies[policy_id={pol.get('policy_id')}].assured_until",
                    "value": str(pol.get("assured_until")),
                    "age_at_date": age,
                    "max_age": int(max_age),
                }
            )

    return issues


def _validate_and_score_items(
    *,
    items: List[Dict[str, Any]],
    transcript_text: str,
    strict: bool,
) -> Dict[str, Any]:
    """Return metrics and a pass/fail boolean.

    In strict mode, we require a direct match only for numeric fields.
    Non-numeric fields count as strict-covered when the extractor marked them present/approximate.
    In non-strict mode, we accept status in {present, approximate} as covered.
    """

    allowed_prefixes = ("Advisor:", "Client:", "Client 1:", "Client 2:")
    bad_lines: List[str] = []
    for raw in (transcript_text or "").splitlines():
        line = raw.strip()
        if not line:
            continue
        if not line.startswith(allowed_prefixes):
            bad_lines.append(line)
            if len(bad_lines) >= 10:
                break

    pii_terms: List[str] = []
    tlow = (transcript_text or "").lower()
    for term in ("social security number", "ssn"):
        if term in tlow:
            pii_terms.append(term)

    counts = {"present": 0, "approximate": 0, "missing": 0, "contradiction": 0, "unknown": 0}
    strict_matched = 0
    strict_failed_target_ids: List[str] = []
    strict_failed_fields: List[Dict[str, Any]] = []
    lenient_failed_fields: List[Dict[str, Any]] = []

    for it in items:
        status = str(it.get("status") or "unknown")
        if status not in counts:
            status = "unknown"
        counts[status] += 1

        if status in {"missing", "contradiction"}:
            tid = str(it.get("target_id") or "")
            lenient_failed_fields.append(
                {
                    "target_id": tid,
                    "field_path": str(it.get("field_path") or ""),
                    "record_type": str(it.get("record_type") or ""),
                    "record_id": it.get("record_id"),
                    "source_value": it.get("source_value"),
                    "status": status,
                }
            )

        field_path = str(it.get("field_path") or "")
        src_val = it.get("source_value")
        src_for_match = round_money_value(src_val, increment=50.0) if is_money_field_path(field_path) else src_val
        if _requires_exact_strict_match(field_path, src_val):
            variants = _value_variants(src_for_match, field_path=field_path)
            strict_match = bool(variants) and _contains_any(transcript_text, variants)
        else:
            strict_match = status in {"present", "approximate"}

        if strict_match:
            strict_matched += 1
        else:
            tid = str(it.get("target_id") or "")
            strict_failed_target_ids.append(tid)
            strict_failed_fields.append(
                {
                    "target_id": tid,
                    "field_path": field_path,
                    "record_type": str(it.get("record_type") or ""),
                    "record_id": it.get("record_id"),
                    "source_value": it.get("source_value"),
                    "status": str(it.get("status") or "unknown"),
                }
            )

    total = len(items)
    covered_lenient = counts["present"] + counts["approximate"]
    covered_strict = strict_matched

    passed_lenient = (counts["missing"] == 0 and counts["contradiction"] == 0)
    passed_strict = (
        covered_strict == total
        and counts["contradiction"] == 0
        and (len(bad_lines) == 0)
        and (len(pii_terms) == 0)
    )
    passed = passed_strict if strict else passed_lenient

    return {
        "passed": bool(passed),
        "strict": bool(strict),
        "format_ok": (len(bad_lines) == 0),
        "bad_transcript_lines": bad_lines,
        "pii_terms_detected": pii_terms,
        "total_targets": total,
        "counts": counts,
        "coverage_lenient": (covered_lenient / total) if total else 0.0,
        "coverage_strict": (covered_strict / total) if total else 0.0,
        # Backwards-compatible: keep the old list of IDs.
        "strict_unmatched_target_ids": strict_failed_target_ids[:200],
        # Preferred: include field names/paths for faster debugging.
        "strict_unmatched_fields": strict_failed_fields[:200],
        # For non-strict runs, these are the fields that actually fail validation (missing/contradiction).
        "lenient_failed_fields": lenient_failed_fields[:200],
    }


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
    # Keep prompts realistic: people don't remember cents.
    rounded = round_money_in_obj(profile, increment=50.0)
    return json.dumps(rounded, ensure_ascii=False, indent=2)


def _json_compact(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


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


def _compact_outline_payload(outline: ConversationOutline) -> Dict[str, Any]:
    # Keep only what is useful for continuity to reduce prompt size.
    phases: List[Dict[str, Any]] = []
    for i, p in enumerate(outline.phases, start=1):
        phases.append(
            {
                "phase_index": i,
                "phase_name": p.phase_name,
                "target_turns": getattr(p, "target_turns", None),
                "objectives": getattr(p, "objectives", None),
                "must_cover_topics": getattr(p, "must_cover_topics", None),
            }
        )
    return {
        "total_target_turns": getattr(outline, "total_target_turns", None),
        "phases": phases,
    }


def _build_rolling_summary(phase_summaries: List[str], *, max_phases: int, max_chars: int) -> str:
    items = [str(s).strip() for s in (phase_summaries or []) if str(s).strip()]
    if max_phases > 0:
        items = items[-int(max_phases) :]
    if not items:
        return ""
    text = "\n".join(f"- {s}" for s in items)
    if max_chars > 0 and len(text) > int(max_chars):
        # Keep the tail (most recent summary items).
        text = text[-int(max_chars) :]
        # Avoid starting mid-word/line if possible.
        cut = text.find("\n")
        if 0 <= cut <= 200:
            text = text[cut + 1 :]
    return text


def _clean_prefixed_lines(text: str, *, household_type: str) -> List[str]:
    allowed_prefixes = {"Advisor:", "Client:"}
    if str(household_type).strip().lower() == "couple":
        allowed_prefixes = {"Advisor:", "Client 1:", "Client 2:"}
    cleaned: List[str] = []
    for raw in (text or "").splitlines():
        line = str(raw).strip()
        if not line:
            continue
        if any(line.startswith(prefix) for prefix in allowed_prefixes):
            cleaned.append(line)
    return cleaned


def _chunk_topic_hint(batch: List[Dict[str, Any]]) -> str:
    if not batch:
        return "next financial topic"
    counts: Dict[str, int] = {}
    for item in batch:
        rt = str(item.get("record_type") or "").strip()
        counts[rt] = counts.get(rt, 0) + 1
    top = max(counts.items(), key=lambda kv: kv[1])[0]
    mapping = {
        "households": "household overview, budget, and high-level constraints",
        "people": "people in the household, ages, and work situation",
        "income_lines": "income sources and pay details",
        "assets": "savings, investments, and property assets",
        "liabilities": "debts, loan balances, and monthly payments",
        "protection_policies": "insurance and protection coverage",
    }
    return mapping.get(top, top.replace("_", " "))


def _sample_text_excerpts(
    text: str,
    *,
    rng: np.random.Generator,
    n_excerpts: int,
    lines_per_excerpt: int,
) -> List[str]:
    lines = [str(line).rstrip() for line in str(text or "").splitlines() if str(line).strip()]
    if not lines:
        return []
    window = max(4, int(lines_per_excerpt))
    if len(lines) <= window:
        return ["\n".join(lines)]
    max_start = max(0, len(lines) - window)
    starts = {0, max_start}
    if n_excerpts > 2:
        for frac in (0.33, 0.66):
            starts.add(max(0, min(max_start, int(round(max_start * frac)))))
    while len(starts) < max(1, int(n_excerpts)):
        starts.add(int(rng.integers(0, max_start + 1)))
    excerpts: List[str] = []
    for start in sorted(starts)[: max(1, int(n_excerpts))]:
        excerpt = "\n".join(lines[start : start + window]).strip()
        if excerpt:
            excerpts.append(excerpt)
    return excerpts


def _load_negative_control_transcripts(repo_root: Path) -> Dict[str, str]:
    base = repo_root / "00_initial_task"
    out: Dict[str, str] = {}
    for name in ["synthetic_transcript1.txt", "synthetic_transcript2.txt"]:
        path = base / name
        if path.exists():
            out[name] = path.read_text(encoding="utf-8")
    return out


class DialogGenerationPipeline:
    def __init__(self, *, repo_root: Optional[Path] = None) -> None:
        self.repo_root = repo_root or default_repo_root()
        self.paths = Paths(repo_root=self.repo_root)
        self.prompts = load_prompts(self.paths.prompt_dir)
        self._negative_control_transcripts = _load_negative_control_transcripts(self.repo_root)

    def _stable_u32(self, s: str) -> int:
        # IMPORTANT: do not use Python's built-in hash(); it is salted per-process
        # and breaks reproducibility across runs/workers.
        d = hashlib.blake2b(str(s).encode("utf-8"), digest_size=4).digest()
        return int.from_bytes(d, byteorder="big", signed=False)

    def _dialog_seed(self, *, base_seed: int, idx: int, household_id: str) -> int:
        # Deterministic per-household seed (stable across runs and worker counts).
        # `idx` is kept only for backward-compat in the signature, but not used
        # to avoid order-dependent seed drift.
        return int((int(base_seed) * 1_000_003 + self._stable_u32(household_id)) % (2**31 - 1))

    def _finalize_with_bridges(
        self,
        *,
        llm: OpenAIResponsesClient,
        system_prompt: str,
        household_type: str,
        chunks_out: List[Dict[str, Any]],
        client1_label: str,
        client2_label: str,
        max_output_tokens: int,
    ) -> str:
        if not chunks_out:
            return ""
        stitched: List[str] = []
        for idx, chunk in enumerate(chunks_out):
            utterances = [str(line).strip() for line in (chunk.get("utterances") or []) if str(line).strip()]
            if idx == 0:
                stitched.extend(utterances)
            else:
                prev = chunks_out[idx - 1]
                bridge_user = render_prompt(
                    self.prompts.chunk_bridge,
                    {
                        "household_type": household_type,
                        "previous_chunk_tail": "\n".join((prev.get("utterances") or [])[-4:]),
                        "next_chunk_head": "\n".join(utterances[:4]),
                        "next_topic_hint": _chunk_topic_hint(chunk.get("targets") or []),
                        "client1_label": client1_label,
                        "client2_label": client2_label or "Client 2:",
                    },
                )
                bridge_text = llm.create_text(
                    system_prompt=system_prompt,
                    user_prompt=bridge_user,
                    max_output_tokens=max_output_tokens,
                )
                stitched.extend(_clean_prefixed_lines(bridge_text, household_type=household_type))
                stitched.extend(utterances)
        return "\n".join(stitched).strip() + "\n"

    def _judge_realism_with_deepseek(
        self,
        *,
        cfg: GenerationConfig,
        dialog_id: str,
        final_transcript: str,
        transcript_skeleton: str,
        household_type: str,
        scenario_name: str,
        rng: np.random.Generator,
    ) -> Optional[Dict[str, Any]]:
        if not bool(getattr(cfg, "deepseek_realism_check", True)):
            return None
        try:
            deepseek = DeepSeekChatClient(
                model=str(getattr(cfg, "deepseek_model", "deepseek-chat")),
                max_output_tokens=int(getattr(cfg, "deepseek_max_output_tokens", 900)),
                temperature=0.0,
            )
        except Exception as exc:
            logger.warning("%s | step=deepseek_judge | skipped | %s", dialog_id, exc)
            return None
        candidate_excerpts = _sample_text_excerpts(final_transcript, rng=rng, n_excerpts=4, lines_per_excerpt=18)
        skeleton_excerpts = _sample_text_excerpts(transcript_skeleton, rng=rng, n_excerpts=2, lines_per_excerpt=12)
        negative_controls: List[Dict[str, Any]] = []
        for name, text in sorted(self._negative_control_transcripts.items()):
            negative_controls.append(
                {
                    "source": name,
                    "excerpts": _sample_text_excerpts(text, rng=rng, n_excerpts=2, lines_per_excerpt=18),
                }
            )
        judge_prompt = render_prompt(
            self.prompts.deepseek_realism_judge,
            {
                "dialog_id": dialog_id,
                "scenario_name": scenario_name,
                "household_type": household_type,
                "candidate_excerpts_json": json.dumps(candidate_excerpts, ensure_ascii=False, indent=2),
                "candidate_skeleton_excerpts_json": json.dumps(skeleton_excerpts, ensure_ascii=False, indent=2),
                "negative_controls_json": json.dumps(negative_controls, ensure_ascii=False, indent=2),
            },
        )
        score = deepseek.create_realism_score_0_100(
            system_prompt="Return exactly one integer from 0 to 100. Output must contain only the number.",
            user_prompt=judge_prompt,
            max_output_tokens=int(getattr(cfg, "deepseek_max_output_tokens", 900)),
        )

        threshold_raw = float(getattr(cfg, "deepseek_realism_threshold", 0.8))
        # Backward-compatible: older configs used 0.0..1.0. Treat that as probability and scale to 0..100.
        threshold = threshold_raw * 100.0 if 0.0 <= threshold_raw <= 1.0 else threshold_raw
        judge: Dict[str, Any] = {
            "realism_score": int(score),
            "threshold": float(threshold),
            # "Выше 90" (strictly greater) by default.
            "passed_threshold": bool(float(score) > float(threshold)),
        }
        judge["meta"] = {
            "dialog_id": dialog_id,
            "scenario_name": scenario_name,
            "household_type": household_type,
            "candidate_excerpt_count": len(candidate_excerpts),
            "negative_control_count": len(negative_controls),
        }
        return judge

    def _generate_one(
        self,
        *,
        cfg: GenerationConfig,
        priors: Dict[str, Any],
        example_transcripts: str,
        profile: Dict[str, Any],
        idx: int,
    ) -> Optional[str]:
        hh_id = str(profile.get("household_id") or profile.get("households", {}).get("household_id") or idx)
        dialog_id = f"DIALOG_{hh_id}"
        log_ctx = f"{dialog_id} | hh={hh_id}"

        dialog_seed = self._dialog_seed(base_seed=int(cfg.seed), idx=idx, household_id=hh_id)
        rng = np.random.default_rng(int(dialog_seed))

        # Use a per-dialog LLM client; safer for threads and enables per-dialog OpenAI seed offsets.
        openai_seed = cfg.model.seed
        if openai_seed is not None:
            openai_seed = int((int(openai_seed) * 1_000_003 + self._stable_u32(hh_id)) % (2**31 - 1))
        llm = OpenAIResponsesClient(
            model=cfg.model.model,
            temperature=cfg.model.temperature,
            max_output_tokens=cfg.model.max_output_tokens,
            seed=openai_seed,
        )

        prof_scenario = _profile_scenario(profile)
        scenario_name = prof_scenario if prof_scenario else sample_scenario(priors, rng)
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

        logger.info("%s | scenario=%s | household_type=%s | seed=%s", log_ctx, scenario_name, hh_type, dialog_seed)
        system_prompt = self.prompts.system

        t0 = time.perf_counter()

        # 1) Personas (shared across modes)
        logger.info("%s | step=personas | start", log_ctx)
        persona_user = render_prompt(
            self.prompts.persona_generation,
            {
                "scenario_name": scenario_name,
                "household_type": hh_type,
                "financial_profile_json": _format_profile_for_prompt(profile),
                "financial_profile_digest": digest,
            },
        )
        personas_obj = llm.create_json(
            system_prompt=system_prompt,
            user_prompt=persona_user,
            schema=Personas,
            max_output_tokens=int(getattr(cfg, "personas_max_output_tokens", cfg.model.max_output_tokens)),
        )
        personas: List[Dict[str, Any]] = [p.model_dump() for p in personas_obj.root]
        logger.info("%s | step=personas | done | dt=%.2fs", log_ctx, time.perf_counter() - t0)

        mode = str(getattr(cfg, "mode", "phases") or "phases").strip().lower()
        if mode not in {"phases", "field_chunks"}:
            mode = "phases"

        # Mode A: Generate transcript by field batches with inline evidence.
        if mode == "field_chunks":
            logger.info("%s | mode=field_chunks | start", log_ctx)
            targets = _build_evidence_targets(
                profile,
                rng=rng,
                shuffle_within_groups=bool(getattr(cfg, "field_chunk_shuffle_within_group", True)),
            )
            batch_size = max(1, int(getattr(cfg, "evidence_batch_size", 10) or 10))
            batches = _batched_targets(
                targets,
                batch_size=batch_size,
                group_by_record_type=bool(getattr(cfg, "field_chunk_group_by_record_type", True)),
            )

            transcript_lines: List[str] = []
            evidence_by_target: Dict[str, Dict[str, Any]] = {}
            chunks_out: List[Dict[str, Any]] = []
            had_chunk_errors = False
            for chunk_index, batch in enumerate(batches, start=1):
                if _count_turns(transcript_lines) >= cfg.max_turns:
                    logger.info("%s | max_turns reached before chunk %s", log_ctx, chunk_index)
                    break

                last_n = max(0, int(getattr(cfg, "context_last_utterances", 60) or 60))
                transcript_window = transcript_lines[-last_n:] if last_n > 0 else []
                chunk_user = render_prompt(
                    self.prompts.field_chunk_generation,
                    {
                        "dialog_id": dialog_id,
                        "scenario_name": scenario_name,
                        "household_type": hh_type,
                        "chunk_index": str(chunk_index),
                        "personas_json": _json_compact(personas),
                        "financial_profile_digest": digest,
                        "targets_json": json.dumps(round_money_in_obj(batch, increment=50.0), ensure_ascii=False, indent=2),
                        "transcript_so_far": "\n".join(transcript_window),
                        "client1_label": client1_label,
                        "client2_label": client2_label or "Client 2:",
                    },
                )
                chunk_res = llm.create_json(
                    system_prompt=system_prompt,
                    user_prompt=chunk_user,
                    schema=FieldChunkGenerationResult,
                    max_output_tokens=int(getattr(cfg, "evidence_max_output_tokens", cfg.model.max_output_tokens)),
                )

                # Deterministic guardrails for a few administrative fields that the model sometimes
                # mislabels as contradiction despite correct source_value and conversation structure.
                try:
                    def _excerpt(text: Any, limit: int = 160) -> str:
                        s = str(text or "")
                        s = " ".join(s.split())
                        return (s[:limit] + "…") if len(s) > limit else s

                    tid_to_target: Dict[str, Dict[str, Any]] = {str(t.get("target_id")): t for t in (batch or []) if isinstance(t, dict)}
                    for ev in chunk_res.evidence_items:
                        tid = str(getattr(ev, "target_id", "") or "")
                        tgt = tid_to_target.get(tid) or {}
                        field_path = str(tgt.get("field_path") or "")
                        st = str(getattr(ev, "status", "") or "").strip().lower()
                        if st not in {"missing", "contradiction"}:
                            continue

                        src = tgt.get("source_value")
                        try:
                            src_n = int(src)
                        except Exception:
                            continue

                        # 1) households.num_adults
                        if field_path == "households.num_adults":
                            if hh_type == "couple" and src_n >= 2:
                                ev.status = "present"  # type: ignore[assignment]
                                if not (ev.notes or "").strip():
                                    ev.notes = "auto-override: couple household implies >=2 adults"  # type: ignore[assignment]
                                logger.info(
                                    "%s | step=field_chunks | override | target_id=%s field_path=households.num_adults %s->present | ev=%s",
                                    log_ctx,
                                    tid,
                                    st,
                                    _excerpt(getattr(ev, "evidence_text", "")),
                                )
                            if hh_type == "single" and src_n == 1:
                                ev.status = "present"  # type: ignore[assignment]
                                if not (ev.notes or "").strip():
                                    ev.notes = "auto-override: single household implies 1 adult"  # type: ignore[assignment]
                                logger.info(
                                    "%s | step=field_chunks | override | target_id=%s field_path=households.num_adults %s->present | ev=%s",
                                    log_ctx,
                                    tid,
                                    st,
                                    _excerpt(getattr(ev, "evidence_text", "")),
                                )
                            continue

                        # 2) people[...].client_no
                        if field_path.endswith(".client_no") and src_n in {1, 2}:
                            ev_text = str(getattr(ev, "evidence_text", "") or "")
                            # Fallback to raw utterances from this chunk (useful when evidence_text is empty).
                            chunk_text = "\n".join([l.strip() for l in (chunk_res.utterances or []) if str(l).strip()])
                            hay = (ev_text + "\n" + chunk_text).lower()
                            # If someone explicitly mentions "client number 0", do NOT override.
                            if ("client number 0" in hay) or ("client no 0" in hay) or ("client #0" in hay):
                                continue
                            wants = f"client {src_n}"
                            if wants in hay:
                                ev.status = "present"  # type: ignore[assignment]
                                if not (ev.notes or "").strip():
                                    ev.notes = "auto-override: explicit Client label matches source_value"  # type: ignore[assignment]
                                logger.info(
                                    "%s | step=field_chunks | override | target_id=%s field_path=%s %s->present | ev=%s",
                                    log_ctx,
                                    tid,
                                    field_path,
                                    st,
                                    _excerpt(ev_text or chunk_text),
                                )
                except Exception:
                    # Never fail generation due to an override bug.
                    pass

                bad_target_ids: List[str] = []
                for it in chunk_res.evidence_items:
                    st = str(getattr(it, "status", "") or "").strip().lower()
                    if st in {"missing", "contradiction"}:
                        bad_target_ids.append(str(it.target_id))
                if bad_target_ids:
                    had_chunk_errors = True

                new_lines = [l.strip() for l in chunk_res.utterances if str(l).strip()]
                # Respect global max_turns.
                remaining = int(cfg.max_turns - _count_turns(transcript_lines))
                if remaining <= 0:
                    break
                if len(new_lines) > remaining:
                    new_lines = new_lines[:remaining]
                transcript_lines.extend(new_lines)

                # Deterministic length + flow helper: add 2 neutral transition turns between chunks.
                # This avoids ultra-short stitched dialogues without introducing new facts or numbers.
                if chunk_index < len(batches):
                    remaining2 = int(cfg.max_turns - _count_turns(transcript_lines))
                    if remaining2 >= 2:
                        if hh_type == "couple" and (client2_label is not None) and (rng.random() < 0.35):
                            ack_speaker = client2_label
                        else:
                            ack_speaker = client1_label
                        transcript_lines.extend(
                            [
                                "Advisor: Okay—got it. Let me note that down.",
                                f"{ack_speaker} Yeah—sounds good.",
                            ]
                        )

                # Merge inline evidence into a global report keyed by target_id.
                for it in chunk_res.evidence_items:
                    evidence_by_target[str(it.target_id)] = it.model_dump()

                chunks_out.append(
                    {
                        "chunk_index": chunk_index,
                        "targets": batch,
                        "utterances": new_lines,
                        "evidence_items": [i.model_dump() for i in chunk_res.evidence_items],
                        "chunk_error_target_ids": bad_target_ids,
                    }
                )

                logger.info(
                    "%s | chunk=%s/%s | turns=+%s total=%s",
                    dialog_id,
                    chunk_index,
                    len(batches),
                    len(new_lines),
                    _count_turns(transcript_lines),
                )

            transcript_text = "\n".join(transcript_lines).strip() + "\n"

            evidence_report: Optional[Dict[str, Any]] = None
            if bool(getattr(cfg, "save_evidence_json", True)):
                # Join targets with inline evidence (no second pass).
                items: List[Dict[str, Any]] = []
                for t in targets:
                    tid = str(t["target_id"])
                    ev = evidence_by_target.get(tid) or {"target_id": tid, "status": "missing", "evidence_text": "", "notes": None}
                    items.append(
                        {
                            "target_id": tid,
                            "record_type": t["record_type"],
                            "record_id": t.get("record_id"),
                            "field_path": t["field_path"],
                            "source_value": t["source_value"],
                            "status": ev.get("status"),
                            "evidence_text": ev.get("evidence_text", ""),
                            "notes": ev.get("notes"),
                        }
                    )

                evidence_report = {
                    "meta": {
                        "dialog_id": dialog_id,
                        "household_id": str(hh_id),
                        "scenario_name": scenario_name,
                        "household_type": hh_type,
                        "num_targets": len(targets),
                        "batch_size": batch_size,
                        "mode": "field_chunks",
                    },
                    "targets": targets,
                    "items": items,
                }

            metrics: Optional[Dict[str, Any]] = None
            if bool(getattr(cfg, "save_metrics_json", True)):
                metrics = _validate_and_score_items(
                    items=(evidence_report or {}).get("items") or [],
                    transcript_text=transcript_text,
                    strict=bool(getattr(cfg, "validation_strict", False)),
                )

            # Deterministic sanity checks (independent of LLM evidence statuses).
            plausibility_issues = _plausibility_issues_for_profile(profile)
            if plausibility_issues:
                if metrics is None:
                    metrics = {
                        "passed": False,
                        "strict": bool(getattr(cfg, "validation_strict", False)),
                        "format_ok": True,
                        "bad_transcript_lines": [],
                        "pii_terms_detected": [],
                        "total_targets": len((evidence_report or {}).get("items") or []),
                        "counts": {"present": 0, "approximate": 0, "missing": 0, "contradiction": 0, "unknown": 0},
                        "coverage_lenient": 0.0,
                        "coverage_strict": 0.0,
                        "strict_unmatched_target_ids": [],
                        "strict_unmatched_fields": [],
                        "lenient_failed_fields": [],
                    }
                # Force fail.
                metrics["passed"] = False
                metrics["plausibility_issues"] = plausibility_issues

            if metrics is not None and not bool(metrics.get("passed")):
                failure_reasons: List[str] = []
                counts = (metrics.get("counts") or {}) if isinstance(metrics.get("counts"), dict) else {}
                if int(counts.get("missing") or 0) > 0:
                    failure_reasons.append("missing")
                if int(counts.get("contradiction") or 0) > 0:
                    failure_reasons.append("contradiction")
                if not bool(metrics.get("format_ok", True)):
                    failure_reasons.append("format")
                if metrics.get("pii_terms_detected"):
                    failure_reasons.append("pii")
                if metrics.get("plausibility_issues"):
                    failure_reasons.append("plausibility")

                strict_run = bool(metrics.get("strict"))
                failing_fields = metrics.get("strict_unmatched_fields") if strict_run else metrics.get("lenient_failed_fields")
                if not isinstance(failing_fields, list):
                    failing_fields = []
                failed_field_paths = [str(f.get("field_path") or "") for f in failing_fields if isinstance(f, dict)]
                failed_target_ids = [str(f.get("target_id") or "") for f in failing_fields if isinstance(f, dict)]

                # Human-readable log for quick diagnosis (no need to open *_metrics.json / *_evidence.json).
                pii_terms = metrics.get("pii_terms_detected")
                if not isinstance(pii_terms, list):
                    pii_terms = []
                bad_lines = metrics.get("bad_transcript_lines")
                if not isinstance(bad_lines, list):
                    bad_lines = []

                logger.warning(
                    "%s | step=validate | FAILED | reasons=%s strict=%s | total=%s covered_lenient=%.3f covered_strict=%.3f | counts=%s | pii_terms=%s",
                    dialog_id,
                    ",".join(failure_reasons) if failure_reasons else "unknown",
                    bool(metrics.get("strict")),
                    metrics.get("total_targets"),
                    float(metrics.get("coverage_lenient") or 0.0),
                    float(metrics.get("coverage_strict") or 0.0),
                    counts,
                    pii_terms,
                )
                if bad_lines:
                    logger.warning("%s | step=validate | bad_transcript_lines=%s", dialog_id, bad_lines[:10])

                # Prefer listing the fields that actually fail in non-strict mode (missing/contradiction),
                # even if strict mode is enabled.
                fields_for_log: List[Dict[str, Any]] = []
                lenient_failed = metrics.get("lenient_failed_fields")
                if isinstance(lenient_failed, list) and lenient_failed:
                    fields_for_log = [f for f in lenient_failed if isinstance(f, dict)]
                else:
                    fields_for_log = [f for f in failing_fields if isinstance(f, dict)]

                # Join evidence details by target_id when available.
                evidence_items = ((evidence_report or {}).get("items") or []) if isinstance(evidence_report, dict) else []
                evidence_by_tid: Dict[str, Dict[str, Any]] = {}
                if isinstance(evidence_items, list):
                    for it in evidence_items:
                        if not isinstance(it, dict):
                            continue
                        tid = str(it.get("target_id") or "").strip()
                        if tid:
                            evidence_by_tid[tid] = it

                def _one_line_excerpt(text: Any, *, limit: int = 180) -> str:
                    s = str(text or "")
                    s = " ".join(s.split())
                    if len(s) > limit:
                        return s[:limit].rstrip() + "…"
                    return s

                max_log_items = int(getattr(cfg, "validation_log_max_items", 25))
                for f in fields_for_log[:max_log_items]:
                    tid = str(f.get("target_id") or "")
                    ev = evidence_by_tid.get(tid) or {}
                    evidence_text = ev.get("evidence_text")
                    notes = ev.get("notes")
                    if pii_terms:
                        evidence_text = "<omitted due to pii_terms_detected>"
                        notes = "<omitted due to pii_terms_detected>"
                    logger.warning(
                        "%s | fail | target_id=%s field_path=%s status=%s source_value=%s | evidence=%s | notes=%s",
                        dialog_id,
                        tid,
                        str(f.get("field_path") or ""),
                        str(f.get("status") or ""),
                        json.dumps(f.get("source_value"), ensure_ascii=False),
                        _one_line_excerpt(evidence_text),
                        _one_line_excerpt(notes),
                    )

                plaus = metrics.get("plausibility_issues")
                if isinstance(plaus, list) and plaus:
                    for issue in plaus[:50]:
                        if not isinstance(issue, dict):
                            continue
                        fp = str(issue.get("field_path") or "")
                        age = issue.get("age_at_date")
                        val = str(issue.get("value") or "")
                        if fp:
                            failed_field_paths.append(f"{fp} (value={val}, age_at_date={age})")

                # Log a one-line, machine-readable report for downstream analysis.
                _append_validation_failure_csv(
                    out_dir=cfg.output_dir,
                    row={
                        "household_id": str(hh_id),
                        "dialog_id": dialog_id,
                        "scenario_name": scenario_name,
                        "mode": "field_chunks",
                        "strict": str(bool(metrics.get("strict"))),
                        "passed": "False",
                        "failure_reasons": ",".join(failure_reasons),
                        "failed_field_paths": "|".join([p for p in failed_field_paths if p])[:50_000],
                        "failed_target_ids": "|".join([t for t in failed_target_ids if t])[:50_000],
                        "counts_present": counts.get("present"),
                        "counts_approximate": counts.get("approximate"),
                        "counts_missing": counts.get("missing"),
                        "counts_contradiction": counts.get("contradiction"),
                        "format_ok": metrics.get("format_ok"),
                        "pii_terms_detected": metrics.get("pii_terms_detected"),
                        "bad_transcript_lines": metrics.get("bad_transcript_lines"),
                    },
                )

                if getattr(cfg, "registry_path", None) is not None:
                    _append_registry_row(
                        path=Path(getattr(cfg, "registry_path")),
                        row={
                            "ts": int(time.time()),
                            "household_id": str(hh_id),
                            "dialog_id": dialog_id,
                            "status": "validation_failed",
                            "scenario_name": scenario_name,
                            "profile_scenario": _profile_scenario(profile),
                            "mode": "field_chunks",
                            "error": json.dumps(metrics, ensure_ascii=False)[:50_000],
                        },
                    )

            if bool(getattr(cfg, "require_validation_pass", True)) and metrics is not None and not bool(metrics.get("passed")):
                # Save artifacts for debugging, then fail fast.
                fail_obj = {
                    "id": dialog_id,
                    "scenario": scenario_name,
                    "financial_profile": profile,
                    "personas": personas,
                    "transcript_skeleton": transcript_text,
                    "chunks": chunks_out,
                    "evidence": evidence_report,
                    "metrics": metrics,
                    "metadata": {
                        "num_turns": _count_turns(transcript_lines),
                        "household_type": hh_type,
                        "scenario_name": scenario_name,
                        "dialog_seed": dialog_seed,
                        "openai_seed": openai_seed,
                        "mode": "field_chunks",
                    },
                }
                out_json_path = cfg.output_dir / f"{dialog_id}.json"
                save_json(out_json_path, fail_obj)
                if evidence_report is not None:
                    save_json(cfg.output_dir / f"{dialog_id}_evidence.json", evidence_report, exclude_none=True)
                if metrics is not None:
                    save_json(cfg.output_dir / f"{dialog_id}_metrics.json", metrics)
                # Intentionally do NOT write .txt for failed validation.
                # Do not raise: just skip this dialog (it is recorded in CSV + registry).
                return None

            # Optional final polish step (adds banter) AFTER validation passes.
            final_transcript = transcript_text
            finalize_requested = bool(getattr(cfg, "finalize_transcript", False))
            finalize_allowed = (not had_chunk_errors) and (metrics is None or bool(metrics.get("passed", True)))
            if finalize_requested and not finalize_allowed:
                logger.info(
                    "%s | step=finalize | skipped | had_chunk_errors=%s metrics_passed=%s",
                    dialog_id,
                    had_chunk_errors,
                    None if metrics is None else bool(metrics.get("passed")),
                )

            if finalize_requested and finalize_allowed:
                logger.info("%s | step=finalize | start", log_ctx)
                strategy = str(getattr(cfg, "finalize_strategy", "realism_merge") or "realism_merge").strip().lower()
                if strategy == "bridges":
                    bridged = self._finalize_with_bridges(
                        llm=llm,
                        system_prompt=system_prompt,
                        household_type=hh_type,
                        chunks_out=chunks_out,
                        client1_label=client1_label,
                        client2_label=client2_label or "Client 2:",
                        max_output_tokens=int(getattr(cfg, "finalize_bridge_max_output_tokens", 500)),
                    )
                    cleaned_lines = _clean_prefixed_lines(bridged, household_type=hh_type)
                else:
                    polish_user = render_prompt(
                        self.prompts.transcript_polish,
                        {
                            "household_type": hh_type,
                            "skeleton_transcript": transcript_text,
                        },
                    )
                    polished = llm.create_text(
                        system_prompt=system_prompt,
                        user_prompt=polish_user,
                        max_output_tokens=int(getattr(cfg, "finalize_max_output_tokens", 2200)),
                    )
                    cleaned_lines = _clean_prefixed_lines(polished, household_type=hh_type)
                if cleaned_lines:
                    final_transcript = "\n".join(cleaned_lines).strip() + "\n"
                logger.info(
                    "%s | step=finalize | done | strategy=%s turns=%s",
                    log_ctx,
                    strategy,
                    _count_turns(cleaned_lines),
                )

            deepseek_realism: Optional[Dict[str, Any]] = None
            if finalize_allowed and bool(getattr(cfg, "deepseek_realism_check", True)):
                try:
                    logger.info("%s | step=deepseek_judge | start", log_ctx)
                    deepseek_realism = self._judge_realism_with_deepseek(
                        cfg=cfg,
                        dialog_id=dialog_id,
                        final_transcript=final_transcript,
                        transcript_skeleton=transcript_text,
                        household_type=hh_type,
                        scenario_name=scenario_name,
                        rng=rng,
                    )
                    if deepseek_realism is not None:
                        logger.info(
                            "%s | step=deepseek_judge | done | score=%s threshold=%s passed_threshold=%s",
                            log_ctx,
                            deepseek_realism.get("realism_score"),
                            deepseek_realism.get("threshold"),
                            bool(deepseek_realism.get("passed_threshold")),
                        )
                except Exception:
                    logger.exception("%s | step=deepseek_judge | failed", log_ctx)

            out_obj = {
                "id": dialog_id,
                "scenario": scenario_name,
                "financial_profile": profile,
                "personas": personas,
                "transcript": final_transcript,
                "transcript_skeleton": transcript_text,
                "chunks": chunks_out,
                "phases": [],
                "evidence": evidence_report,
                "metrics": metrics,
                "deepseek_realism": deepseek_realism,
                "metadata": {
                    "num_turns": _count_turns(final_transcript.splitlines()),
                    "household_type": hh_type,
                    "scenario_name": scenario_name,
                    "dialog_seed": dialog_seed,
                    "openai_seed": openai_seed,
                    "mode": "field_chunks",
                    "had_chunk_errors": had_chunk_errors,
                    "finalize_requested": finalize_requested,
                    "finalize_applied": bool(finalize_requested and finalize_allowed),
                    "deepseek_realism_checked": deepseek_realism is not None,
                    "deepseek_realism_passed": bool((deepseek_realism or {}).get("passed_threshold")),
                },
            }

            out_json_path = cfg.output_dir / f"{dialog_id}.json"
            save_json(out_json_path, out_obj)
            if evidence_report is not None:
                save_json(cfg.output_dir / f"{dialog_id}_evidence.json", evidence_report, exclude_none=True)
            if metrics is not None:
                save_json(cfg.output_dir / f"{dialog_id}_metrics.json", metrics)
            if deepseek_realism is not None:
                save_json(cfg.output_dir / f"{dialog_id}_deepseek_judge.json", deepseek_realism)
            if cfg.save_txt:
                save_text(cfg.output_dir / f"{dialog_id}.txt", final_transcript)
            if bool((deepseek_realism or {}).get("passed_threshold")):
                pass_dir = cfg.output_dir / str(getattr(cfg, "deepseek_pass_subdir", "realism_passed"))
                save_json(pass_dir / f"{dialog_id}.json", out_obj)
                if cfg.save_txt:
                    save_text(pass_dir / f"{dialog_id}.txt", final_transcript)
                save_json(pass_dir / f"{dialog_id}_deepseek_judge.json", deepseek_realism)

            logger.info(
                "%s | wrote=%s | turns=%s | total_dt=%.2fs",
                dialog_id,
                out_json_path.name,
                out_obj["metadata"]["num_turns"],
                time.perf_counter() - t0,
            )
            return dialog_id

        # Mode B (default): multi-phase generation

        # 2) Outline
        t1 = time.perf_counter()
        logger.info("%s | step=outline | start", log_ctx)
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
            max_output_tokens=int(getattr(cfg, "outline_max_output_tokens", cfg.model.max_output_tokens)),
        )
        outline_compact_json = json.dumps(_compact_outline_payload(outline), ensure_ascii=False, indent=2)
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
        phase_summaries: List[str] = []

        used_person_ids: set[str] = set()
        used_income_line_ids: set[str] = set()
        used_asset_ids: set[str] = set()
        used_liability_ids: set[str] = set()
        used_policy_ids: set[str] = set()

        for phase_idx, phase in enumerate(outline.phases):
            if _count_turns(transcript_lines) >= cfg.max_turns:
                logger.info("%s | max_turns reached before phase %s", log_ctx, phase_idx + 1)
                break

            logger.info(
                "%s | phase=%s/%s | name=%s | start",
                dialog_id,
                phase_idx + 1,
                len(outline.phases),
                phase.phase_name,
            )
            tp = time.perf_counter()

            last_n = max(0, int(getattr(cfg, "context_last_utterances", 60) or 60))
            transcript_window = transcript_lines[-last_n:] if last_n > 0 else []
            summary_text = _build_rolling_summary(
                phase_summaries,
                max_phases=max(0, int(getattr(cfg, "context_summary_last_phases", 8) or 8)),
                max_chars=max(0, int(getattr(cfg, "context_summary_max_chars", 3500) or 3500)),
            )
            phase_user = render_prompt(
                self.prompts.phase_generation,
                {
                    "scenario_name": scenario_name,
                    "household_type": hh_type,
                    "phase_index": str(phase_idx + 1),
                    "phase_name": phase.phase_name,
                    "phase_json": _json_compact(phase.model_dump()),
                    "outline_json": outline_compact_json,
                    "personas_json": _json_compact(personas),
                    "state_json": _json_compact(state.to_dict()),
                    "transcript_summary_so_far": summary_text,
                    "transcript_so_far": "\n".join(transcript_window),
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
                max_output_tokens=int(getattr(cfg, "phase_max_output_tokens", cfg.model.max_output_tokens)),
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
                    "personas_json": _json_compact(personas),
                    "financial_profile_digest": digest,
                    "previous_state_json": _json_compact(state.to_dict()),
                    "new_utterances": "\n".join(new_lines),
                },
            )
            state_res = llm.create_json(
                system_prompt=system_prompt,
                user_prompt=state_user,
                schema=StateUpdateResult,
                max_output_tokens=int(getattr(cfg, "state_max_output_tokens", cfg.model.max_output_tokens)),
            )

            state_dict = state_res.state.model_dump()
            state_dict["misunderstood_terms"] = _normalize_misunderstood_terms(state_dict.get("misunderstood_terms"))
            state = ConversationState(**state_dict)
            if getattr(state_res, "phase_summary", None):
                phase_summaries.append(str(state_res.phase_summary))

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
                "target_turns": min(120, max(25, remaining_turn_budget)),
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
                    "phase_json": _json_compact(gap_phase),
                    "outline_json": outline_compact_json,
                    "personas_json": _json_compact(personas),
                    "state_json": _json_compact(state.to_dict()),
                    "transcript_summary_so_far": _build_rolling_summary(
                        phase_summaries,
                        max_phases=max(0, int(getattr(cfg, "context_summary_last_phases", 8) or 8)),
                        max_chars=max(0, int(getattr(cfg, "context_summary_max_chars", 3500) or 3500)),
                    ),
                    "transcript_so_far": "\n".join(
                        transcript_lines[-max(0, int(getattr(cfg, "context_last_utterances", 60) or 60)) :]
                    ),
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
                max_output_tokens=int(getattr(cfg, "phase_max_output_tokens", cfg.model.max_output_tokens)),
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
                    "personas_json": _json_compact(personas),
                    "financial_profile_digest": digest,
                    "previous_state_json": _json_compact(state.to_dict()),
                    "new_utterances": "\n".join(new_lines),
                },
            )
            state_res = llm.create_json(
                system_prompt=system_prompt,
                user_prompt=state_user,
                schema=StateUpdateResult,
                max_output_tokens=int(getattr(cfg, "state_max_output_tokens", cfg.model.max_output_tokens)),
            )
            state_dict = state_res.state.model_dump()
            state_dict["misunderstood_terms"] = _normalize_misunderstood_terms(state_dict.get("misunderstood_terms"))
            state = ConversationState(**state_dict)
            if getattr(state_res, "phase_summary", None):
                phase_summaries.append(str(state_res.phase_summary))

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

        evidence_report: Optional[Dict[str, Any]] = None
        evidence_posthoc = bool(getattr(cfg, "evidence_posthoc", True))
        if bool(getattr(cfg, "save_evidence_json", True)) and evidence_posthoc:
            te0 = time.perf_counter()
            logger.info("%s | step=evidence | start", log_ctx)
            targets = _build_evidence_targets(profile)
            batch_size = max(1, int(getattr(cfg, "evidence_batch_size", 25) or 25))
            batches = _chunk_list(targets, batch_size)
            all_items: List[Dict[str, Any]] = []
            for bi, batch in enumerate(batches, start=1):
                evidence_user = render_prompt(
                    self.prompts.evidence_extraction,
                    {
                        "dialog_id": dialog_id,
                        "household_id": str(hh_id),
                        "scenario_name": scenario_name,
                        "household_type": hh_type,
                        "financial_profile_digest": digest,
                        "evidence_targets_json": json.dumps(batch, ensure_ascii=False, indent=2),
                        "transcript_text": transcript_text,
                    },
                )
                batch_res = llm.create_json(
                    system_prompt=system_prompt,
                    user_prompt=evidence_user,
                    schema=EvidenceExtractionBatchResult,
                    max_output_tokens=int(getattr(cfg, "evidence_max_output_tokens", 1800)),
                )
                all_items.extend([i.model_dump() for i in batch_res.items])
                logger.info(
                    "%s | step=evidence | batch=%s/%s | items=%s",
                    dialog_id,
                    bi,
                    len(batches),
                    len(batch_res.items),
                )

            evidence_report = {
                "meta": {
                    "dialog_id": dialog_id,
                    "household_id": str(hh_id),
                    "scenario_name": scenario_name,
                    "household_type": hh_type,
                    "num_targets": len(targets),
                    "batch_size": batch_size,
                    "mode": "phases_posthoc",
                },
                "targets": targets,
                "items": all_items,
            }
            logger.info("%s | step=evidence | done | dt=%.2fs", log_ctx, time.perf_counter() - te0)

        out_obj = {
            "id": dialog_id,
            "scenario": scenario_name,
            "financial_profile": profile,
            "personas": personas,
            "transcript": transcript_text,
            "phases": phases_out,
            "evidence": evidence_report,
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
        if evidence_report is not None:
            save_json(cfg.output_dir / f"{dialog_id}_evidence.json", evidence_report, exclude_none=True)
        if cfg.save_txt:
            save_text(cfg.output_dir / f"{dialog_id}.txt", transcript_text)

        logger.info(
            "%s | wrote=%s | turns=%s | total_dt=%.2fs",
            log_ctx,
            out_json_path.name,
            out_obj["metadata"]["num_turns"],
            time.perf_counter() - t0,
        )

        if getattr(cfg, "registry_path", None) is not None:
            _append_registry_row(
                path=Path(getattr(cfg, "registry_path")),
                row={
                    "ts": int(time.time()),
                    "household_id": str(hh_id),
                    "dialog_id": dialog_id,
                    "status": "success",
                    "scenario_name": scenario_name,
                    "profile_scenario": prof_scenario,
                    "mode": str(getattr(cfg, "mode", "")),
                    "error": "",
                },
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

        registry_path = getattr(cfg, "registry_path", None)
        selected_profiles = _select_profiles(
            profiles=profiles,
            n=int(getattr(cfg, "n", 1) or 1),
            seed=int(getattr(cfg, "seed", 42) or 42),
            sample_mode=str(getattr(cfg, "sample_mode", "sequential") or "sequential"),
            income_bins=int(getattr(cfg, "income_bins", 3) or 3),
            assets_bins=int(getattr(cfg, "assets_bins", 3) or 3),
            output_dir=getattr(cfg, "output_dir", None),
            registry_path=(Path(registry_path) if registry_path is not None else None),
            skip_existing=bool(getattr(cfg, "skip_existing", True)),
            registry_skip_statuses=str(getattr(cfg, "registry_skip_statuses", "success") or "success"),
        )

        n = len(selected_profiles)
        logger.info(
            "Generating %s transcripts | sample_mode=%s | skip_existing=%s | registry=%s",
            n,
            str(getattr(cfg, "sample_mode", "sequential")),
            bool(getattr(cfg, "skip_existing", True)),
            str(registry_path) if registry_path is not None else "(none)",
        )

        profiles = selected_profiles
        workers = max(1, int(getattr(cfg, "workers", 1) or 1))
        continue_on_error = bool(getattr(cfg, "continue_on_error", True))
        errored: List[str] = []
        skipped: List[str] = []

        if workers == 1 or n <= 1:
            for idx, profile in enumerate(profiles):
                try:
                    dialog_id = self._generate_one(
                        cfg=cfg,
                        priors=priors,
                        example_transcripts=example_transcripts,
                        profile=profile,
                        idx=idx,
                    )
                    if dialog_id:
                        hh_id = str(dialog_id).replace("DIALOG_", "", 1)
                        logger.info("done: %s | hh=%s", dialog_id, hh_id)
                    else:
                        hh_id = _profile_household_id(profile) or str(idx)
                        skipped.append(f"DIALOG_{hh_id}")
                        logger.info("skipped (validation_failed): DIALOG_%s", hh_id)
                except Exception:
                    hh_id = _profile_household_id(profile) or str(idx)
                    dialog_id = f"DIALOG_{hh_id}"
                    errored.append(dialog_id)
                    logger.exception("failed: %s", dialog_id)
                    if not continue_on_error:
                        raise
            if skipped:
                logger.info("Skipped dialogs (validation_failed): %s", skipped[:50])
            if errored:
                logger.warning("Errored dialogs: %s", errored[:50])
            return

        logger.info("Generating %s transcripts with workers=%s", n, workers)
        with ThreadPoolExecutor(max_workers=workers, thread_name_prefix="dialog") as ex:
            fut_to_dialog: Dict[Any, str] = {}
            futures = []
            for idx, profile in enumerate(profiles):
                hh_id = _profile_household_id(profile) or str(idx)
                fut = ex.submit(
                    self._generate_one,
                    cfg=cfg,
                    priors=priors,
                    example_transcripts=example_transcripts,
                    profile=profile,
                    idx=idx,
                )
                fut_to_dialog[fut] = f"DIALOG_{hh_id}"
                futures.append(fut)
            for fut in as_completed(futures):
                try:
                    dialog_id = fut.result()
                    if dialog_id:
                        hh_id = str(dialog_id).replace("DIALOG_", "", 1)
                        logger.info("done: %s | hh=%s", dialog_id, hh_id)
                    else:
                        dialog_id2 = fut_to_dialog.get(fut) or "(unknown)"
                        skipped.append(str(dialog_id2))
                        logger.info("skipped (validation_failed): %s", dialog_id2)
                except Exception:
                    dialog_id = fut_to_dialog.get(fut) or "(unknown)"
                    logger.exception("dialog generation failed: %s", dialog_id)
                    errored.append(str(dialog_id))
                    if not continue_on_error:
                        raise

        if skipped:
            logger.info("Skipped dialogs (validation_failed): %s", skipped[:50])
        if errored:
            logger.warning("Errored dialogs: %s", errored[:50])
