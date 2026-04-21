from __future__ import annotations

import argparse
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Set, Tuple


_FIELD_PATH_RE = re.compile(
    r"^(?P<entity>[a-z_]+)(\[(?P<selector>[^\]]+)\])?\.(?P<field>[a-zA-Z0-9_]+)$"
)


def _repo_root() -> Path:
    # export_grounded_profiles.py lives in <repo>/03_data_extraction/src/
    return Path(__file__).resolve().parents[2]


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, obj: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _iter_evidence_paths(dialogs_dir: Path) -> Iterable[Path]:
    yield from sorted(dialogs_dir.glob("DIALOG_*_evidence.json"))


def _parse_field_path(field_path: str) -> Optional[Tuple[str, Optional[str], Optional[str], str]]:
    """Return (entity, selector_key, selector_value, field_name)."""

    s = str(field_path or "").strip()
    if not s:
        return None

    m = _FIELD_PATH_RE.match(s)
    if not m:
        return None

    entity = str(m.group("entity") or "").strip()
    selector = m.group("selector")
    field = str(m.group("field") or "").strip()

    if selector is None:
        return (entity, None, None, field)

    selector_s = str(selector).strip()
    if "=" not in selector_s:
        return None

    k, v = selector_s.split("=", 1)
    selector_key = str(k).strip() or None
    selector_value = str(v).strip() or None
    if not selector_key or not selector_value:
        return None
    return (entity, selector_key, selector_value, field)


def _pk_key_for_entity(entity: str) -> str:
    # Keep consistent with schema.json and 03 pairing logic.
    if entity == "households":
        return "household_id"
    if entity == "people":
        return "person_id"
    if entity == "income_lines":
        return "income_line_id"
    if entity == "assets":
        return "asset_id"
    if entity == "liabilities":
        return "liability_id"
    if entity == "protection_policies":
        return "policy_id"
    return "id"


_CLIENT_LABEL_RE = re.compile(r"Client(?:\s+(?P<n>[12]))?:", re.IGNORECASE)


def _last_client_no(text: str) -> Optional[int]:
    last: Optional[int] = None
    for m in _CLIENT_LABEL_RE.finditer(str(text or "")):
        n = m.group("n")
        if n is None:
            last = 1
        else:
            try:
                last = int(n)
            except Exception:
                pass
    return last


def _should_keep_evidence_item(
    *,
    entity: str,
    field_name: str,
    selector_value: Optional[str],
    source_value: Any,
    evidence_text: str,
) -> bool:
    text = str(evidence_text or "").lower()
    value_s = str(source_value or "").strip().lower()
    selector_s = str(selector_value or "").strip().upper()
    if entity == "people" and field_name == "occupation_group":
        if value_s in {"retired", "inactive"}:
            return False
        last_client = _last_client_no(text)
        if selector_s.endswith("_P1") and last_client not in {1, None}:
            return False
        if selector_s.endswith("_P2") and last_client != 2:
            return False

    if entity == "assets" and field_name == "provider_type":
        weak_platform_words = ("shown on", "view through", "grouped", "visible on", "advisor platform", "retirement platform")
        strong_holder_words = ("held at", "at the bank", "at the brokerage", "at the insurer", "through the bank", "with the bank")
        if any(w in text for w in weak_platform_words) and not any(w in text for w in strong_holder_words):
            return False
        if value_s in {"advisor_platform", "retirement_platform"} and any(
            w in text for w in ("bank account", "at the bank", "held at a bank", "held at the bank", "brokerage account", "at a brokerage")
        ):
            return False

    return True


@dataclass
class GroundedBuildStats:
    dialogs_seen: int = 0
    dialogs_written: int = 0
    items_seen: int = 0
    items_used: int = 0
    dialogs_missing_items: int = 0
    dialogs_missing_meta: int = 0
    dialogs_missing_household_id: int = 0


def build_grounded_profile_from_evidence(
    evidence: Dict[str, Any],
    *,
    include_statuses: Set[str],
) -> Optional[Dict[str, Any]]:
    meta = evidence.get("meta")
    if not isinstance(meta, dict):
        return None

    household_id = str(meta.get("household_id") or "").strip()
    if not household_id:
        return None

    households: Dict[str, Any] = {"household_id": household_id}
    lists_by_entity: Dict[str, Dict[str, Dict[str, Any]]] = {
        "people": {},
        "income_lines": {},
        "assets": {},
        "liabilities": {},
        "protection_policies": {},
    }

    items = evidence.get("items")
    if not isinstance(items, list):
        items = []

    for it in items:
        if not isinstance(it, dict):
            continue

        status = str(it.get("status") or "").strip().lower()
        if status not in include_statuses:
            continue

        field_path = str(it.get("field_path") or "").strip()
        parsed = _parse_field_path(field_path)
        if not parsed:
            continue
        entity, _selector_key, selector_value, field_name = parsed

        source_value = it.get("source_value")
        evidence_text = str(it.get("evidence_text") or "")

        if not _should_keep_evidence_item(
            entity=entity,
            field_name=field_name,
            selector_value=selector_value,
            source_value=source_value,
            evidence_text=evidence_text,
        ):
            continue

        if entity == "households":
            households[field_name] = source_value
            continue

        if selector_value is None:
            continue

        pk = _pk_key_for_entity(entity)
        ent_map = lists_by_entity.get(entity)
        if ent_map is None:
            continue

        rec_opt = ent_map.get(selector_value)
        if rec_opt is None:
            rec: Dict[str, Any] = {pk: selector_value, "household_id": household_id}
            ent_map[selector_value] = rec
        else:
            rec = rec_opt

        rec[field_name] = source_value

    return {
        "household_id": household_id,
        "households": households,
        "people": list(lists_by_entity["people"].values()),
        "income_lines": list(lists_by_entity["income_lines"].values()),
        "assets": list(lists_by_entity["assets"].values()),
        "liabilities": list(lists_by_entity["liabilities"].values()),
        "protection_policies": list(lists_by_entity["protection_policies"].values()),
        "_ground_truth_is_grounded": True,
    }


def main() -> int:
    ap = argparse.ArgumentParser(description="Export dialog-grounded financial profiles from *_evidence.json artifacts")

    repo_root = _repo_root()
    default_dialogs_dir = repo_root / "02_dialogs_generation" / "artifacts" / "dialogs"
    default_out_json = repo_root / "02_dialogs_generation" / "artifacts" / "grounded_financial_profiles.json"

    ap.add_argument(
        "--dialogs-dir",
        type=Path,
        default=default_dialogs_dir,
        help="Directory containing DIALOG_*_evidence.json (default: <repo>/02_dialogs_generation/artifacts/dialogs)",
    )
    ap.add_argument(
        "--out-json",
        type=Path,
        default=default_out_json,
        help="Output JSON (list of sparse grounded profiles) (default: <repo>/02_dialogs_generation/artifacts/grounded_financial_profiles.json)",
    )
    ap.add_argument(
        "--include-approximate",
        action="store_true",
        help="If set, include evidence items with status=approximate as ground-truth fields",
    )
    args = ap.parse_args()

    dialogs_dir = Path(args.dialogs_dir)
    out_json = Path(args.out_json)

    include_statuses: Set[str] = {"present"}
    if bool(args.include_approximate):
        include_statuses.add("approximate")

    stats = GroundedBuildStats()
    out: List[Dict[str, Any]] = []

    for ev_path in _iter_evidence_paths(dialogs_dir):
        stats.dialogs_seen += 1

        evidence_obj = _read_json(ev_path)
        if not isinstance(evidence_obj, dict):
            continue

        meta = evidence_obj.get("meta")
        if not isinstance(meta, dict):
            stats.dialogs_missing_meta += 1
            continue

        household_id = str(meta.get("household_id") or "").strip()
        if not household_id:
            stats.dialogs_missing_household_id += 1
            continue

        items_any = evidence_obj.get("items")
        if not isinstance(items_any, list):
            stats.dialogs_missing_items += 1
            items_any = []

        stats.items_seen += len([x for x in items_any if isinstance(x, dict)])

        profile = build_grounded_profile_from_evidence(evidence_obj, include_statuses=include_statuses)
        if profile is None:
            continue

        used = 0
        hh = profile.get("households") or {}
        if isinstance(hh, dict):
            used += max(0, len(hh) - 1)  # minus household_id
        for k in ("people", "income_lines", "assets", "liabilities", "protection_policies"):
            rows = profile.get(k) or []
            if isinstance(rows, list):
                for r in rows:
                    if not isinstance(r, dict):
                        continue
                    used += max(0, len(r) - 2)  # minus pk + household_id

        stats.items_used += used
        out.append(profile)
        stats.dialogs_written += 1

    _write_json(out_json, out)
    report = {
        "dialogs_dir": str(dialogs_dir),
        "out_json": str(out_json),
        "include_statuses": sorted(include_statuses),
        **stats.__dict__,
        "profiles": len(out),
    }
    print(json.dumps(report, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
