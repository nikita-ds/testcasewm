from __future__ import annotations

import argparse
import json
import os
from dataclasses import asdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from coerce import CoerceIssue, coerce_record, compute_derived_household_fields
from env_utils import load_dotenv_if_present
from llm_client import OpenAIResponsesClient
from normalization_bridge import canonicalize_categorical, normalize_profile_values
from schema_spec import DataSchema, schema_compact_for_prompt


ENTITY_KEYS: Tuple[str, ...] = (
    "households",
    "people",
    "income_lines",
    "assets",
    "liabilities",
    "protection_policies",
)

TARGETED_RESCUE_ENTITY_KEYS: Tuple[str, ...] = (
    "liabilities",
    "protection_policies",
)


def _read_text(path: Path, max_chars: int = 120_000) -> str:
    txt = path.read_text(encoding="utf-8", errors="replace")
    if len(txt) > max_chars:
        return txt[:max_chars]
    return txt


def _find_dialog_txts(realism_passed_dir: Path) -> List[Path]:
    if not realism_passed_dir.exists():
        return []
    return sorted(realism_passed_dir.glob("*.txt"))


def _dialog_id_from_path(p: Path) -> str:
    # e.g. DIALOG_HH001473.txt -> DIALOG_HH001473
    return p.stem


def _household_id_from_dialog_id(dialog_id: str) -> str:
    return dialog_id[len("DIALOG_") :] if dialog_id.startswith("DIALOG_") else dialog_id


def _load_prompt_template(name: str) -> str:
    base = Path(__file__).resolve().parent
    path = base / "prompts" / name
    return path.read_text(encoding="utf-8")


def _build_system_prompt(schema_compact: Dict[str, Any]) -> str:
    schema_json = json.dumps(schema_compact, ensure_ascii=False)
    template = _load_prompt_template("extraction_system_prompt.txt")
    return template.replace("{{SCHEMA_JSON}}", schema_json)


def _build_targeted_rescue_prompt(schema_compact: Dict[str, Any]) -> str:
    schema_json = json.dumps(schema_compact, ensure_ascii=False)
    return (
        "You are repairing missing structured extraction from a client-advisor dialog.\n"
        "You MUST output ONLY valid JSON. No markdown. No explanations.\n\n"
        "Task:\n"
        "- Extract ONLY the requested entity arrays.\n"
        "- If the dialog clearly mentions a liability or protection policy, output a record even if some fields are unknown.\n"
        "- Use only information stated in the dialog.\n"
        "- For categorical fields, choose the closest allowed value from the schema.\n"
        "- For dates, use YYYY-MM-DD when explicitly stated.\n"
        "- Do not output any entities other than liabilities and protection_policies.\n\n"
        "Output format requirements:\n"
        "- Return one JSON object with exactly these keys: liabilities, protection_policies\n"
        "- Each key must map to an array, possibly empty.\n\n"
        "Target schema (compact JSON):\n"
        f"{schema_json}"
    )


def _try_load_json(path: Path) -> Optional[Dict[str, Any]]:
    try:
        if not path.exists():
            return None
        obj = json.loads(path.read_text(encoding="utf-8"))
        return obj if isinstance(obj, dict) else None
    except Exception:
        return None


def _uniq_strs(vals: List[Any]) -> List[str]:
    out: List[str] = []
    seen: set[str] = set()
    for v in vals:
        if v is None:
            continue
        s = str(v).strip()
        if not s or s in seen:
            continue
        seen.add(s)
        out.append(s)
    return out


def _allowed_values_from_priors(priors: Dict[str, Any]) -> Dict[str, List[str]]:
    """Build allowed categorical domains keyed by field_path (entity.field)."""

    out: Dict[str, List[str]] = {}

    def put(field_path: str, values: List[Any], *, canonicalize: bool = True) -> None:
        vals = _uniq_strs(values)
        if not vals:
            return
        if canonicalize:
            canon = canonicalize_categorical(field_path, vals)
            if isinstance(canon, list):
                vals = _uniq_strs(canon)
        out[field_path] = vals

    cat = priors.get("categoricals") or {}
    if isinstance(cat, dict):
        # These are maps of value -> probability.
        for field, fp in (
            ("marital_status", "households.marital_status"),
            ("residence_state", "households.residence_state"),
            ("risk_tolerance", "households.risk_tolerance"),
            ("tax_bracket_band", "households.tax_bracket_band"),
        ):
            d = cat.get(field)
            if isinstance(d, dict):
                put(fp, list(d.keys()), canonicalize=True)

    gen = priors.get("generator_params") or {}
    if isinstance(gen, dict):
        scenarios = gen.get("scenarios")
        if isinstance(scenarios, list):
            put("households.scenario", scenarios, canonicalize=True)

        objectives = gen.get("objectives")
        if isinstance(objectives, list):
            # multichoice values are per-item tokens
            put("households.investment_objectives", objectives, canonicalize=True)

        meta = priors.get("meta") or {}
        if isinstance(meta, dict):
            country = meta.get("country")
            market = meta.get("market")
            if country is not None:
                put("households.country", [country], canonicalize=True)
            if market is not None:
                put("households.market", [market], canonicalize=True)

        income_model = gen.get("income_lines_model") or {}
        if isinstance(income_model, dict):
            sources = income_model.get("sources")
            if isinstance(sources, list):
                put("income_lines.source_type", sources, canonicalize=True)
            freq = income_model.get("frequency")
            if isinstance(freq, dict):
                freq_vals = freq.get("values")
                if isinstance(freq_vals, list):
                    put("income_lines.frequency", freq_vals, canonicalize=True)

        person_model = gen.get("person_model") or {}
        if isinstance(person_model, dict):
            occ = person_model.get("occupation_group")
            if isinstance(occ, dict):
                all_occ: List[Any] = []
                for k in ("primary", "secondary"):
                    v = occ.get(k)
                    if isinstance(v, list):
                        all_occ.extend(v)
                put("people.occupation_group", all_occ, canonicalize=True)

            soh = person_model.get("state_of_health")
            if isinstance(soh, dict):
                values = soh.get("values")
                if isinstance(values, list):
                    put("people.state_of_health", values, canonicalize=True)

        asset_model = gen.get("asset_model") or {}
        if isinstance(asset_model, dict):
            providers = asset_model.get("provider_types")
            if isinstance(providers, list):
                put("assets.provider_type", providers, canonicalize=True)

        protection_model = gen.get("protection_model") or {}
        if isinstance(protection_model, dict):
            policy_types = protection_model.get("policy_types")
            if isinstance(policy_types, list):
                put("protection_policies.policy_type", policy_types, canonicalize=True)

        # Employment status domain is defined by the status model probabilities.
        person_status_model = gen.get("person_status_model") or {}
        if isinstance(person_status_model, dict):
            adult_probs = person_status_model.get("adult_probs")
            if isinstance(adult_probs, dict):
                put("people.employment_status", list(adult_probs.keys()), canonicalize=True)

    # Safe canonical domains (these are used throughout profiles and normalization).
    for fp in (
        "assets.owner",
        "income_lines.owner",
        "protection_policies.owner",
    ):
        put(fp, ["client_1", "client_2", "joint"], canonicalize=True)

    put("income_lines.net_or_gross", ["gross", "net"], canonicalize=True)
    put("people.role", ["primary", "spouse_partner"], canonicalize=True)

    # Asset and liability type domains (currently fixed in the generator).
    put(
        "assets.asset_type",
        ["brokerage", "retirement", "cash", "alternatives", "property"],
        canonicalize=True,
    )
    put(
        "assets.subtype",
        ["taxable", "401k_ira", "bank", "private_markets", "primary_residence"],
        canonicalize=True,
    )
    put("liabilities.type", ["mortgage", "loan", "credit_card"], canonicalize=True)

    # Small people domains (avoid huge lists like nationality/place_of_birth).
    put("people.gender", ["male", "female", "non_binary"], canonicalize=True)
    put("people.legal_sex", ["male", "female", "non_binary"], canonicalize=True)
    put("people.pronouns", ["he_him", "she_her", "they_them"], canonicalize=True)
    put("people.title", ["Mr", "Ms", "Mrs", "Dr", "Mx"], canonicalize=True)

    return out


def _extract_json(
    *,
    client: OpenAIResponsesClient,
    system_prompt: str,
    user_prompt: str,
    max_output_tokens: int,
) -> Dict[str, Any]:
    return client.create_json(
        max_output_tokens=max_output_tokens,
        system_prompt=system_prompt,
        user_prompt=user_prompt,
    )


def _coerce_and_filter(
    *,
    raw: Dict[str, Any],
    schema: DataSchema,
) -> Tuple[Dict[str, Any], List[CoerceIssue]]:
    """Coerce values to schema types and drop unknown fields/entities."""

    out: Dict[str, Any] = {}
    issues: List[CoerceIssue] = []

    for entity in schema.entities.values():
        raw_list = raw.get(entity.name)
        if raw_list is None:
            # Ensure key exists with empty list to make outputs consistent.
            out[entity.name] = []
            continue
        if not isinstance(raw_list, list):
            # If the model outputs a dict for single record, accept it.
            if isinstance(raw_list, dict):
                raw_list = [raw_list]
            else:
                continue

        coerced_records: List[Dict[str, Any]] = []
        for i, rec in enumerate(raw_list):
            if not isinstance(rec, dict):
                continue
            coerced, rec_issues = coerce_record(
                entity=entity.name,
                record_index=i,
                record=rec,
                fields=entity.field_map(),
            )
            issues.extend(rec_issues)
            coerced_records.append(coerced)

        if entity.name == "households" and coerced_records:
            coerced_records[0] = compute_derived_household_fields(coerced_records[0])

        # Always include the entity key, even if empty.
        out[entity.name] = coerced_records

    return out, issues


def _basic_coverage_summary(extracted: Dict[str, Any]) -> Dict[str, Any]:
    entity_counts: Dict[str, int] = {}
    field_counts: Dict[str, int] = {}

    for entity_name, records in extracted.items():
        if not isinstance(records, list):
            continue
        entity_counts[entity_name] = len(records)
        for rec in records:
            if not isinstance(rec, dict):
                continue
            for k, v in rec.items():
                if v is None:
                    continue
                field_counts[f"{entity_name}.{k}"] = field_counts.get(f"{entity_name}.{k}", 0) + 1

    return {"entity_counts": entity_counts, "field_counts": field_counts}


def _write_jsonl(path: Path, rows: List[Dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")


def _write_json(path: Path, obj: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _unwrap_model_output(obj: Any) -> Any:
    """Unwrap common wrapper shapes returned by LLMs.

    We expect an object with top-level entity keys (households, people, ...),
    but models often return {"result": {...}} or {"extracted": {...}}.
    """

    if not isinstance(obj, dict):
        return obj

    # If already contains any entity key, assume it's the right level.
    if any(k in obj for k in ENTITY_KEYS):
        return obj

    for k in ("result", "extracted", "data", "output", "profile"):
        v = obj.get(k)
        if isinstance(v, dict):
            # recurse once
            if any(ek in v for ek in ENTITY_KEYS):
                return v
            # Some models return nested wrappers like {result: {data: {...}}}
            for k2 in ("result", "extracted", "data", "output", "profile"):
                v2 = v.get(k2)
                if isinstance(v2, dict) and any(ek in v2 for ek in ENTITY_KEYS):
                    return v2

    return obj


def _entity_total(summary: Dict[str, Any]) -> int:
    entity_counts = summary.get("entity_counts")
    if not isinstance(entity_counts, dict):
        return 0
    return sum(int(v) for v in entity_counts.values() if isinstance(v, int))


def _as_records(v: Any) -> List[Dict[str, Any]]:
    if v is None:
        return []
    if isinstance(v, list):
        return [x for x in v if isinstance(x, dict)]
    if isinstance(v, dict):
        return [v]
    return []


def _valid_existing_extract(path: Path) -> bool:
    try:
        obj = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return False

    if not isinstance(obj, dict):
        return False

    if not any(k in obj for k in ENTITY_KEYS):
        return False

    summary = _basic_coverage_summary(obj)
    return _entity_total(summary) > 0


def _retry_user_prompt(base_prompt: str, attempt_no: int) -> str:
    if attempt_no <= 1:
        return base_prompt
    retry_note = (
        "\n\nIMPORTANT OUTPUT REQUIREMENT:\n"
        "Return exactly one JSON object with these top-level keys: "
        "households, people, income_lines, assets, liabilities, protection_policies.\n"
        "Do not return a bare list. Do not return a partial object. "
        "Use empty arrays for missing entities."
    )
    return base_prompt + retry_note


def _targeted_retry_user_prompt(base_prompt: str, attempt_no: int) -> str:
    if attempt_no <= 1:
        return base_prompt
    retry_note = (
        "\n\nIMPORTANT OUTPUT REQUIREMENT:\n"
        'Return exactly {"liabilities": [...], "protection_policies": [...]}.\n'
        "Do not return households, people, income_lines, or assets.\n"
        "If a liability/policy is clearly present in the dialog, do not leave the array empty."
    )
    return base_prompt + retry_note


def _slice_schema_compact(schema_compact: Dict[str, Any], entity_names: Tuple[str, ...]) -> Dict[str, Any]:
    entities = schema_compact.get("entities")
    if not isinstance(entities, dict):
        return {"entities": {}}
    return {
        "snapshot_date": schema_compact.get("snapshot_date"),
        "entities": {name: entities[name] for name in entity_names if name in entities},
    }


def _dialog_mentions_liability(dialog_text: str, households: List[Dict[str, Any]]) -> bool:
    hh = households[0] if households else {}
    for key in (
        "monthly_debt_cost_total",
        "loan_outstanding_total",
        "mortgage_outstanding_total",
        "non_mortgage_outstanding_total",
    ):
        v = hh.get(key)
        if isinstance(v, (int, float)) and float(v) > 0:
            return True
    if hh.get("has_mortgage_or_loan") is True:
        return True

    t = dialog_text.lower()
    hints = (
        "mortgage balance",
        "mortgage payment",
        "monthly debt",
        "loan payment",
        "final payment date",
        "interest rate",
        "credit card",
        "car loan",
        "student loan",
    )
    return any(h in t for h in hints)


def _dialog_mentions_policy(dialog_text: str) -> bool:
    t = dialog_text.lower()
    hints = (
        "life insurance",
        "disability",
        "long-term care",
        "long term care",
        "ltc",
        "policy type",
        "coverage amount",
        "amount assured",
        "monthly premium",
        "premium is",
        "covered until",
        "protection policies",
    )
    return any(h in t for h in hints)


def _needs_targeted_rescue(extracted: Dict[str, Any], dialog_text: str) -> bool:
    households = _as_records(extracted.get("households"))
    liabilities = _as_records(extracted.get("liabilities"))
    policies = _as_records(extracted.get("protection_policies"))
    need_liabilities = not liabilities and _dialog_mentions_liability(dialog_text, households)
    need_policies = not policies and _dialog_mentions_policy(dialog_text)
    return need_liabilities or need_policies


def _merge_targeted_entities(base: Dict[str, Any], rescue: Dict[str, Any]) -> Dict[str, Any]:
    out = dict(base)
    for key in TARGETED_RESCUE_ENTITY_KEYS:
        existing = _as_records(out.get(key))
        rescued = _as_records(rescue.get(key))
        if not existing and rescued:
            out[key] = rescued
    return out


def _extract_targeted_rescue(
    *,
    client: OpenAIResponsesClient,
    schema: DataSchema,
    schema_compact: Dict[str, Any],
    household_id: str,
    dialog_id: str,
    dialog_text: str,
    out_dir: Path,
    max_output_tokens: int,
) -> Tuple[Dict[str, Any], List[CoerceIssue]]:
    system_prompt = _build_targeted_rescue_prompt(
        _slice_schema_compact(schema_compact, TARGETED_RESCUE_ENTITY_KEYS)
    )
    user_prompt = f"household_id: {household_id}\n\n{dialog_text}"
    retry_limit = max(1, int(os.environ.get("EXTRACTION_TARGETED_RETRY_LIMIT", "2")))
    last_raw: Any = {}

    for attempt_no in range(1, retry_limit + 1):
        raw = _extract_json(
            client=client,
            system_prompt=system_prompt,
            user_prompt=_targeted_retry_user_prompt(user_prompt, attempt_no),
            max_output_tokens=min(max_output_tokens, 2500),
        )
        _write_json(out_dir.joinpath(f"{dialog_id}.targeted_raw.attempt_{attempt_no}.json"), raw)

        raw_unwrapped = _unwrap_model_output(raw)
        if not isinstance(raw_unwrapped, dict):
            last_raw = raw
            continue

        targeted_raw = {k: raw_unwrapped.get(k, []) for k in TARGETED_RESCUE_ENTITY_KEYS}
        targeted_schema = DataSchema(snapshot_date=schema.snapshot_date, entities={k: schema.entities[k] for k in TARGETED_RESCUE_ENTITY_KEYS})
        extracted, issues = _coerce_and_filter(raw=targeted_raw, schema=targeted_schema)
        extracted = normalize_profile_values(schema=schema, household_id=household_id, profile=extracted)
        if any(_as_records(extracted.get(k)) for k in TARGETED_RESCUE_ENTITY_KEYS):
            return extracted, issues
        last_raw = raw

    raise RuntimeError(f"Targeted rescue failed for {dialog_id}; last_raw_type={type(last_raw).__name__}")


def _extract_validated_profile(
    *,
    client: OpenAIResponsesClient,
    schema: DataSchema,
    system_prompt: str,
    user_prompt: str,
    household_id: str,
    out_dir: Path,
    dialog_id: str,
    max_output_tokens: int,
) -> Tuple[Any, Any, Dict[str, Any], List[CoerceIssue], Dict[str, Any]]:
    retry_limit = max(1, int(os.environ.get("EXTRACTION_RETRY_LIMIT", "3")))
    last_reason = "unknown"
    last_raw: Any = {}

    for attempt_no in range(1, retry_limit + 1):
        raw = _extract_json(
            client=client,
            system_prompt=system_prompt,
            user_prompt=_retry_user_prompt(user_prompt, attempt_no),
            max_output_tokens=max_output_tokens,
        )
        raw_attempt_path = out_dir.joinpath(f"{dialog_id}.raw.attempt_{attempt_no}.json")
        _write_json(raw_attempt_path, raw)

        raw_unwrapped = _unwrap_model_output(raw)
        extracted, issues = _coerce_and_filter(
            raw=raw_unwrapped if isinstance(raw_unwrapped, dict) else {},
            schema=schema,
        )
        extracted = normalize_profile_values(schema=schema, household_id=household_id, profile=extracted)
        summary = _basic_coverage_summary(extracted)

        if not isinstance(raw_unwrapped, dict):
            last_reason = "invalid_root_shape"
            last_raw = raw
            continue
        if not any(k in raw_unwrapped for k in ENTITY_KEYS):
            last_reason = "missing_entity_keys"
            last_raw = raw
            continue
        if _entity_total(summary) == 0:
            last_reason = "empty_extraction"
            last_raw = raw
            continue

        return raw, raw_unwrapped, extracted, issues, summary

    raise RuntimeError(f"Invalid extraction after {retry_limit} attempts: {last_reason}; last_raw_type={type(last_raw).__name__}")


def _process_one_dialog(
    *,
    client: OpenAIResponsesClient,
    schema: DataSchema,
    schema_compact: Dict[str, Any],
    system_prompt: str,
    dialog_txt_path: Path,
    out_dir: Path,
    max_output_tokens: int,
) -> Tuple[Dict[str, Any], List[Dict[str, Any]], Dict[str, int]]:
    dialog_id = _dialog_id_from_path(dialog_txt_path)
    household_id = _household_id_from_dialog_id(dialog_id)
    out_path = out_dir.joinpath(f"{dialog_id}.extracted.json")
    raw_path = out_dir.joinpath(f"{dialog_id}.raw.json")

    dialog_text = _read_text(dialog_txt_path)

    user_prompt = f"household_id: {household_id}\n\n" + dialog_text

    raw, raw_unwrapped, extracted, issues, summary = _extract_validated_profile(
        client=client,
        schema=schema,
        system_prompt=system_prompt,
        user_prompt=user_prompt,
        household_id=household_id,
        out_dir=out_dir,
        dialog_id=dialog_id,
        max_output_tokens=max_output_tokens,
    )

    if _needs_targeted_rescue(extracted, dialog_text):
        try:
            rescued, rescue_issues = _extract_targeted_rescue(
                client=client,
                schema=schema,
                schema_compact=schema_compact,
                household_id=household_id,
                dialog_id=dialog_id,
                dialog_text=dialog_text,
                out_dir=out_dir,
                max_output_tokens=max_output_tokens,
            )
            extracted = _merge_targeted_entities(extracted, rescued)
            issues.extend(rescue_issues)
            summary = _basic_coverage_summary(extracted)
        except Exception:
            pass

    _write_json(raw_path, raw)

    raw_unwrapped = _unwrap_model_output(raw)
    if isinstance(raw_unwrapped, dict) and raw_unwrapped is not raw:
        # Keep the unwrapped version too (helps when raw is a wrapper).
        _write_json(out_dir.joinpath(f"{dialog_id}.raw_unwrapped.json"), raw_unwrapped)

    coverage_counts: Dict[str, int] = {}
    for k, v in summary.get("field_counts", {}).items():
        coverage_counts[k] = coverage_counts.get(k, 0) + int(v)

    _write_json(out_path, extracted)

    row = {
        "dialog_id": dialog_id,
        "status": "ok",
        "extracted_path": str(out_path),
        "summary": summary,
    }
    issues_rows = [{"dialog_id": dialog_id, **asdict(iss)} for iss in issues]
    return row, issues_rows, coverage_counts


def main() -> int:
    # Must load .env before argparse defaults read os.environ.
    load_dotenv_if_present(Path(__file__).resolve().parent)

    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--schema",
        default=str(Path("..").joinpath("01_data_generation", "config", "schema.json")),
        help="Path to schema.json (default: ../01_data_generation/config/schema.json)",
    )
    ap.add_argument(
        "--priors",
        default=str(Path("..").joinpath("01_data_generation", "config", "priors.json")),
        help="Path to priors.json (default: ../01_data_generation/config/priors.json)",
    )
    ap.add_argument(
        "--dialogs-dir",
        default=str(Path("..").joinpath("02_dialogs_generation", "artifacts", "dialogs", "realism_passed")),
        help="Directory with realism-passed dialog .txt files",
    )
    ap.add_argument(
        "--out-dir",
        default=str(Path("artifacts").joinpath("extracted")),
        help="Output directory (default: artifacts/extracted)",
    )
    ap.add_argument(
        "--limit",
        type=int,
        default=int(os.environ.get("EXTRACTION_LIMIT", "0")),
        help="Max dialogs to process (0 = all). Can also be set via EXTRACTION_LIMIT",
    )
    ap.add_argument("--model", default=os.environ.get("OPENAI_MODEL", "gpt-5.2"))
    ap.add_argument("--max-output-tokens", type=int, default=6000)
    ap.add_argument("--skip-existing", action="store_true")
    ap.add_argument(
        "--workers",
        type=int,
        default=int(os.environ.get("EXTRACTION_WORKERS", "1")),
        help="Number of parallel extraction workers (default: EXTRACTION_WORKERS or 1)",
    )

    args = ap.parse_args()

    schema_path = Path(args.schema)
    priors_path = Path(args.priors)
    dialogs_dir = Path(args.dialogs_dir)
    out_dir = Path(args.out_dir)

    schema = DataSchema.load(schema_path)
    priors = _try_load_json(priors_path)
    allowed_values_by_field_path = _allowed_values_from_priors(priors) if priors else {}
    schema_compact = schema_compact_for_prompt(schema, allowed_values_by_field_path=allowed_values_by_field_path)
    system_prompt = _build_system_prompt(schema_compact)

    txt_files = _find_dialog_txts(dialogs_dir)
    if args.limit and args.limit > 0:
        txt_files = txt_files[: args.limit]

    client = OpenAIResponsesClient(model=args.model, max_output_tokens=args.max_output_tokens)

    rows: List[Dict[str, Any]] = []
    all_issues: List[Dict[str, Any]] = []
    coverage_aggregate: Dict[str, int] = {}

    to_process: List[Path] = []
    for txt_path in txt_files:
        dialog_id = _dialog_id_from_path(txt_path)
        out_path = out_dir.joinpath(f"{dialog_id}.extracted.json")
        if args.skip_existing and out_path.exists() and _valid_existing_extract(out_path):
            continue
        to_process.append(txt_path)

    workers = max(1, int(args.workers))
    if workers == 1:
        for txt_path in to_process:
            dialog_id = _dialog_id_from_path(txt_path)
            try:
                row, issues_rows, coverage_counts = _process_one_dialog(
                    client=client,
                    schema=schema,
                    schema_compact=schema_compact,
                    system_prompt=system_prompt,
                    dialog_txt_path=txt_path,
                    out_dir=out_dir,
                    max_output_tokens=args.max_output_tokens,
                )
                rows.append(row)
                all_issues.extend(issues_rows)
                for k, v in coverage_counts.items():
                    coverage_aggregate[k] = coverage_aggregate.get(k, 0) + int(v)
            except Exception as e:
                rows.append({"dialog_id": dialog_id, "status": "llm_error", "error": str(e)})
    else:
        with ThreadPoolExecutor(max_workers=workers) as ex:
            futs = {
                ex.submit(
                    _process_one_dialog,
                    client=client,
                    schema=schema,
                    schema_compact=schema_compact,
                    system_prompt=system_prompt,
                    dialog_txt_path=txt_path,
                    out_dir=out_dir,
                    max_output_tokens=args.max_output_tokens,
                ): txt_path
                for txt_path in to_process
            }

            for fut in as_completed(futs):
                txt_path = futs[fut]
                dialog_id = _dialog_id_from_path(txt_path)
                try:
                    row, issues_rows, coverage_counts = fut.result()
                    rows.append(row)
                    all_issues.extend(issues_rows)
                    for k, v in coverage_counts.items():
                        coverage_aggregate[k] = coverage_aggregate.get(k, 0) + int(v)
                except Exception as e:
                    rows.append({"dialog_id": dialog_id, "status": "llm_error", "error": str(e)})

    _write_jsonl(out_dir.joinpath("extracted_index.jsonl"), rows)
    _write_json(out_dir.joinpath("coerce_issues.json"), all_issues)
    _write_json(out_dir.joinpath("coverage_aggregate.json"), coverage_aggregate)

    report = {
        "dialogs_seen": len(_find_dialog_txts(dialogs_dir)),
        "dialogs_processed": len(rows),
        "ok": sum(1 for r in rows if r.get("status") == "ok"),
        "llm_error": sum(1 for r in rows if r.get("status") == "llm_error"),
        "issues": len(all_issues),
        "out_dir": str(out_dir),
    }
    _write_json(out_dir.joinpath("report.json"), report)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
