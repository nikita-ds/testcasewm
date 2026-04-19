from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

from normalization_bridge import normalize_profile_values
from schema_spec import DataSchema


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _iter_jsonl(path: Path) -> Iterable[Dict[str, Any]]:
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            s = line.strip()
            if not s:
                continue
            obj = json.loads(s)
            if isinstance(obj, dict):
                yield obj


def _write_jsonl(path: Path, rows: Iterable[Dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")


def _as_entity_list(v: Any) -> List[Dict[str, Any]]:
    if v is None:
        return []
    if isinstance(v, list):
        return [x for x in v if isinstance(x, dict)]
    if isinstance(v, dict):
        return [v]
    return []


def _get_household_id_from_dialog_id(dialog_id: str) -> str:
    if dialog_id.startswith("DIALOG_"):
        return dialog_id[len("DIALOG_") :]
    return dialog_id


def _load_extracted_for_dialog(extracted_dir: Path, dialog_id: str) -> Dict[str, Any]:
    p = extracted_dir / f"{dialog_id}.extracted.json"
    if not p.exists():
        return {}
    obj = _read_json(p)
    return obj if isinstance(obj, dict) else {}


def _merge_entities(
    *,
    schema: DataSchema,
    ground_truth_profile: Dict[str, Any],
    extracted_profile: Dict[str, Any],
) -> Dict[str, Any]:
    merged: Dict[str, Any] = {}

    for entity_name, entity in schema.entities.items():
        gt_list = _as_entity_list(ground_truth_profile.get(entity_name))
        ex_list = _as_entity_list(extracted_profile.get(entity_name))

        if entity_name == "households":
            target_n = max(len(gt_list), len(ex_list), 1)
        else:
            target_n = max(len(gt_list), len(ex_list))

        if target_n == 0:
            merged[entity_name] = []
            continue

        records: List[Dict[str, Any]] = []
        for i in range(target_n):
            gt_rec = gt_list[i] if i < len(gt_list) else {}
            ex_rec = ex_list[i] if i < len(ex_list) else {}

            out_rec: Dict[str, Any] = {}
            for field in entity.fields:
                out_rec[field.name] = {
                    "ground_truth": gt_rec.get(field.name),
                    "extracted": ex_rec.get(field.name),
                }
            records.append(out_rec)

        merged[entity_name] = records

    return merged


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--schema",
        default=str(Path("..").joinpath("01_data_generation", "config", "schema.json")),
        help="Path to schema.json (default: ../01_data_generation/config/schema.json)",
    )
    ap.add_argument(
        "--pairs",
        default=str(Path("artifacts").joinpath("ground_truth_pairs.jsonl")),
        help="Path to ground-truth pairs JSONL (default: artifacts/ground_truth_pairs.jsonl)",
    )
    ap.add_argument(
        "--extracted-dir",
        default=str(Path("artifacts").joinpath("extracted")),
        help="Directory with per-dialog extracted JSONs (default: artifacts/extracted)",
    )
    ap.add_argument(
        "--out",
        default=str(Path("artifacts").joinpath("joint_dataset.jsonl")),
        help="Output JSONL (default: artifacts/joint_dataset.jsonl)",
    )
    ap.add_argument("--limit", type=int, default=0)

    args = ap.parse_args()

    schema = DataSchema.load(Path(args.schema))
    pairs_path = Path(args.pairs)
    extracted_dir = Path(args.extracted_dir)
    out_path = Path(args.out)

    if not pairs_path.exists():
        raise SystemExit(f"Missing pairs file: {pairs_path}")

    rows: List[Dict[str, Any]] = []
    for i, pair in enumerate(_iter_jsonl(pairs_path)):
        if args.limit and i >= args.limit:
            break

        dialog_id = str(pair.get("dialog_id") or "").strip()
        hh_id = str(pair.get("household_id") or "").strip()
        if not hh_id and dialog_id:
            hh_id = _get_household_id_from_dialog_id(dialog_id)

        dialog_text = pair.get("dialog")
        if not isinstance(dialog_text, str):
            dialog_text = ""

        gt_profile = pair.get("profile")
        gt_profile = gt_profile if isinstance(gt_profile, dict) else {}
        gt_profile = normalize_profile_values(schema=schema, household_id=hh_id, profile=gt_profile)

        extracted = _load_extracted_for_dialog(extracted_dir, dialog_id) if dialog_id else {}
        extracted = normalize_profile_values(schema=schema, household_id=hh_id, profile=extracted)

        merged_schema = _merge_entities(
            schema=schema,
            ground_truth_profile=gt_profile,
            extracted_profile=extracted,
        )

        rows.append(
            {
                "household_id": hh_id,
                "dialog_id": dialog_id,
                "dialog": dialog_text,
                "schema": merged_schema,
            }
        )

    _write_jsonl(out_path, rows)
    print(json.dumps({"out": str(out_path), "rows": len(rows)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
