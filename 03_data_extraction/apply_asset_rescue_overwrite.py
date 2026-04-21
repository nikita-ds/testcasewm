from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Dict, List, Optional

from normalization_bridge import normalize_profile_values
from schema_spec import DataSchema


CORRECTION_FIELDS = ("owner", "is_joint", "provider_type", "asset_type", "subtype")


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, obj: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _as_records(v: Any) -> List[Dict[str, Any]]:
    if v is None:
        return []
    if isinstance(v, list):
        return [x for x in v if isinstance(x, dict)]
    if isinstance(v, dict):
        return [v]
    return []


def _num(v: Any) -> Optional[float]:
    if isinstance(v, bool) or v is None:
        return None
    if isinstance(v, (int, float)):
        return float(v)
    s = str(v).strip().replace(",", "").replace("$", "")
    if not s:
        return None
    try:
        return float(s)
    except Exception:
        return None


def _same_value(a: Dict[str, Any], b: Dict[str, Any]) -> bool:
    av = _num(a.get("value"))
    bv = _num(b.get("value"))
    if av is None or bv is None:
        return False
    return abs(av - bv) <= max(abs(av) * 1e-6, 1e-9)


def apply_asset_rescue_overwrite(base: Dict[str, Any], rescue: Dict[str, Any]) -> Dict[str, Any]:
    out = dict(base)
    assets = [dict(a) for a in _as_records(out.get("assets"))]
    rescue_assets = _as_records(rescue.get("assets"))
    if not assets or not rescue_assets:
        out["assets"] = assets
        return out

    used: set[int] = set()
    for asset in assets:
        match_idx = None
        for idx, candidate in enumerate(rescue_assets):
            if idx in used:
                continue
            if _same_value(asset, candidate):
                match_idx = idx
                break
        if match_idx is None:
            continue
        used.add(match_idx)
        matched = rescue_assets[match_idx]
        for field in CORRECTION_FIELDS:
            value = matched.get(field)
            if value is not None and value != "":
                asset[field] = value

    out["assets"] = assets
    return out


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Apply high-confidence asset rescue overwrites to existing extraction artifacts."
    )
    ap.add_argument(
        "--schema",
        default=str(Path("..").joinpath("01_data_generation", "config", "schema.json")),
        help="Path to schema.json (default: ../01_data_generation/config/schema.json)",
    )
    ap.add_argument(
        "--input-extracted-dir",
        default=str(Path("artifacts").joinpath("extracted")),
        help="Directory with baseline extraction artifacts",
    )
    ap.add_argument(
        "--output-extracted-dir",
        default=str(Path("artifacts").joinpath("extracted_improved")),
        help="Directory for improved extraction artifacts",
    )
    args = ap.parse_args()

    schema = DataSchema.load(Path(args.schema))
    input_dir = Path(args.input_extracted_dir)
    output_dir = Path(args.output_extracted_dir)

    processed = 0
    changed = 0
    for base_path in sorted(input_dir.glob("DIALOG_*.extracted.json")):
        dialog_id = base_path.name[: -len(".extracted.json")]
        household_id = dialog_id[len("DIALOG_") :] if dialog_id.startswith("DIALOG_") else dialog_id
        rescue_path = input_dir / f"{dialog_id}.asset_owner_raw.attempt_1.json"
        base = _read_json(base_path)
        if not isinstance(base, dict):
            continue
        improved = base
        if rescue_path.exists():
            rescue = _read_json(rescue_path)
            if isinstance(rescue, dict):
                improved = apply_asset_rescue_overwrite(base, rescue)
        improved = normalize_profile_values(schema=schema, household_id=household_id, profile=improved)
        if improved != base:
            changed += 1
        _write_json(output_dir / f"{dialog_id}.extracted.json", improved)
        processed += 1

    print(json.dumps({"processed": processed, "changed": changed, "out_dir": str(output_dir)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
