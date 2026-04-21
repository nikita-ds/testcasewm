from __future__ import annotations

import importlib.util
from pathlib import Path
from typing import Any, Dict, List

from schema_spec import DataSchema


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _load_dialogs_normalization_module():
    """Load 02_dialogs_generation/src/normalization.py by file path.

    The folder name starts with a digit, so it can't be imported as a normal
    Python package.
    """

    mod_path = _repo_root() / "02_dialogs_generation" / "src" / "normalization.py"
    if not mod_path.exists():
        raise RuntimeError(f"Missing normalization module at {mod_path}")

    spec = importlib.util.spec_from_file_location("dialogs_normalization", mod_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Failed to load spec for {mod_path}")

    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)  # type: ignore[attr-defined]
    return module


_dialogs_norm = _load_dialogs_normalization_module()


canonicalize_categorical = getattr(_dialogs_norm, "canonicalize_categorical")
canonicalize_multichoice = getattr(_dialogs_norm, "canonicalize_multichoice")
canonicalize_record_ids = getattr(_dialogs_norm, "canonicalize_record_ids")


def _infer_people_fields(rec: Dict[str, Any]) -> Dict[str, Any]:
    out = dict(rec)

    person_id = str(out.get("person_id") or "").strip().upper()
    role = str(out.get("role") or "").strip().lower()
    client_no = out.get("client_no")
    employment_status = str(out.get("employment_status") or "").strip().lower()
    occupation_group = str(out.get("occupation_group") or "").strip().lower()

    if client_no is None:
        if person_id.endswith("_P1"):
            out["client_no"] = 1
        elif person_id.endswith("_P2"):
            out["client_no"] = 2
        elif role == "primary":
            out["client_no"] = 1
        elif role == "spouse_partner":
            out["client_no"] = 2

    if not out.get("role"):
        if out.get("client_no") == 1:
            out["role"] = "primary"
        elif out.get("client_no") == 2:
            out["role"] = "spouse_partner"

    if not employment_status and occupation_group in {"retired", "inactive"}:
        out["employment_status"] = occupation_group

    return out


def _infer_asset_fields(rec: Dict[str, Any]) -> Dict[str, Any]:
    out = dict(rec)

    owner = str(out.get("owner") or "").strip().lower()
    is_joint = out.get("is_joint")

    if not owner:
        if is_joint is True:
            out["owner"] = "joint"
    elif is_joint is None:
        if owner == "joint":
            out["is_joint"] = True
        elif owner in {"client_1", "client_2"}:
            out["is_joint"] = False

    return out


def normalize_profile_values(*, schema: DataSchema, household_id: str, profile: Dict[str, Any]) -> Dict[str, Any]:
    """Normalize categorical/multichoice values and canonicalize PK formats.

    This is used both on extracted and ground-truth profiles before scoring.
    """

    out: Dict[str, Any] = {}

    for ent_name, ent in schema.entities.items():
        records_any = profile.get(ent_name)
        if records_any is None:
            out[ent_name] = []
            continue
        if isinstance(records_any, dict):
            records: List[Dict[str, Any]] = [records_any]
        elif isinstance(records_any, list):
            records = [r for r in records_any if isinstance(r, dict)]
        else:
            out[ent_name] = []
            continue

        norm_records: List[Dict[str, Any]] = []
        for rec in records:
            rec_out = dict(rec)

            # Canonicalize primary key formatting to improve pairing.
            rec_out = canonicalize_record_ids(
                entity=ent_name,
                household_id=household_id,
                record=rec_out,
                primary_key=ent.primary_key,
            )

            for field in ent.fields:
                if field.name not in rec_out:
                    continue
                v = rec_out.get(field.name)
                field_path = f"{ent_name}.{field.name}"

                if field.type == "multichoice":
                    rec_out[field.name] = canonicalize_multichoice(field_path, v)
                elif field.type == "categorical":
                    rec_out[field.name] = canonicalize_categorical(field_path, v)
                else:
                    # Leave strings/numbers/dates alone (coercion handles types).
                    pass

            if ent_name == "people":
                rec_out = _infer_people_fields(rec_out)
            elif ent_name == "assets":
                rec_out = _infer_asset_fields(rec_out)

            norm_records.append(rec_out)

        out[ent_name] = norm_records

    return out
