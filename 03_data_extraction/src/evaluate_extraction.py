from __future__ import annotations

import argparse
import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple, TypeGuard

try:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt  # noqa: E402
except Exception:  # pragma: no cover - local minimal environments may skip plots
    plt = None  # type: ignore[assignment]

from normalization_bridge import normalize_profile_values
from scoring_config import default_exclusions_path, load_exclusions, should_score_field
from schema_spec import DEFAULT_ENTITY_ORDER, DataSchema, EntitySpec, FieldSpec


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


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


def _as_records(v: Any) -> List[Dict[str, Any]]:
    if v is None:
        return []
    if isinstance(v, list):
        return [x for x in v if isinstance(x, dict)]
    if isinstance(v, dict):
        return [v]
    return []


def _is_number(x: Any) -> TypeGuard[int | float]:
    return isinstance(x, (int, float)) and not isinstance(x, bool)


def _norm_str(x: Any) -> str:
    if x is None:
        return ""
    return str(x).strip()


def _norm_multichoice(x: Any) -> List[str]:
    if x is None:
        return []
    if isinstance(x, list):
        return sorted({str(i).strip() for i in x if str(i).strip()})
    s = str(x).strip()
    if not s:
        return []
    # ground truth uses '|', sometimes extracted may use commas
    parts: List[str] = []
    for chunk in s.replace(",", "|").split("|"):
        c = chunk.strip()
        if c:
            parts.append(c)
    return sorted(set(parts))


def _values_match(
    *,
    gt: Any,
    ex: Any,
    field: FieldSpec,
    numeric_rel_tol: float,
) -> bool:
    # Treat both missing as match.
    if gt is None and ex is None:
        return True

    t = str(field.type)

    if t in {"continuous", "integer", "integer_nullable"}:
        if gt is None or ex is None:
            return False
        if not (_is_number(gt) and _is_number(ex)):
            return False
        gtf = float(gt)
        exf = float(ex)
        tol = max(abs(gtf) * float(numeric_rel_tol), 1e-9)
        return abs(exf - gtf) <= tol

    if t in {"boolean"}:
        if gt is None or ex is None:
            return False
        return bool(gt) == bool(ex)

    if t in {"date", "date_nullable"}:
        if gt is None and ex is None:
            return True
        return _norm_str(gt) == _norm_str(ex)

    if t == "multichoice":
        return _norm_multichoice(gt) == _norm_multichoice(ex)

    # default string-ish compare
    return _norm_str(gt).lower() == _norm_str(ex).lower()


@dataclass(frozen=True)
class FieldCell:
    ground_truth: Any
    extracted: Any
    match: bool


def _index_records_by_pk(records: List[Dict[str, Any]], pk: str) -> Dict[str, Dict[str, Any]]:
    out: Dict[str, Dict[str, Any]] = {}
    for r in records:
        v = r.get(pk)
        if v is None:
            continue
        key = str(v)
        if key:
            out[key] = r
    return out


def _truthy_env(name: str, default: bool = False) -> bool:
    try:
        v = str(os.environ.get(name, "") or "").strip().lower()
    except Exception:
        v = ""
    if not v:
        return default
    return v in {"1", "true", "yes", "y", "on"}


def _income_line_pair_score(
    *,
    gt: Dict[str, Any],
    ex: Dict[str, Any],
    numeric_rel_tol: float,
) -> float:
    """Heuristic similarity score for pairing income_lines records.

    The extracted side may generate unstable income_line_id values; pairing by
    content avoids counting ordering/ID swaps as value mismatches.
    """

    score = 0.0

    def _eq(a: Any, b: Any) -> bool:
        return _norm_str(a).lower() == _norm_str(b).lower()

    if _eq(gt.get("owner"), ex.get("owner")):
        score += 3.0
    if _eq(gt.get("source_type"), ex.get("source_type")):
        score += 4.0
    if _eq(gt.get("frequency"), ex.get("frequency")):
        score += 2.0
    if _eq(gt.get("net_or_gross"), ex.get("net_or_gross")):
        score += 1.0

    g = gt.get("amount_annualized")
    e = ex.get("amount_annualized")
    if _is_number(g) and _is_number(e):
        gtf = float(g)
        exf = float(e)
        tol = max(abs(gtf) * float(numeric_rel_tol), 1e-9)
        if abs(exf - gtf) <= tol:
            score += 4.0
        else:
            # Still give a tiny score so we can break ties consistently.
            denom = max(abs(gtf), 1.0)
            score += max(0.0, 0.5 - abs(exf - gtf) / denom)

    return score


def _asset_pair_score(
    *,
    gt: Dict[str, Any],
    ex: Dict[str, Any],
    numeric_rel_tol: float,
) -> float:
    """Heuristic similarity score for pairing assets records.

    Extracted asset_id values can be unstable; pairing by content avoids
    counting ordering/ID swaps as value mismatches.
    """

    score = 0.0

    def _eq(a: Any, b: Any) -> bool:
        return _norm_str(a).lower() == _norm_str(b).lower()

    if _eq(gt.get("owner"), ex.get("owner")):
        score += 2.0
    if _eq(gt.get("asset_type"), ex.get("asset_type")):
        score += 3.0
    if _eq(gt.get("subtype"), ex.get("subtype")):
        score += 2.0
    if _eq(gt.get("provider_type"), ex.get("provider_type")):
        score += 1.0

    g = gt.get("value")
    e = ex.get("value")
    if _is_number(g) and _is_number(e):
        gtf = float(g)
        exf = float(e)
        tol = max(abs(gtf) * float(numeric_rel_tol), 1e-9)
        if abs(exf - gtf) <= tol:
            score += 8.0
        else:
            denom = max(abs(gtf), 1.0)
            score += max(0.0, 1.0 - abs(exf - gtf) / denom)

    return score


def _liability_pair_score(
    *,
    gt: Dict[str, Any],
    ex: Dict[str, Any],
    numeric_rel_tol: float,
) -> float:
    score = 0.0

    def _eq(a: Any, b: Any) -> bool:
        return _norm_str(a).lower() == _norm_str(b).lower()

    if _eq(gt.get("type"), ex.get("type")):
        score += 4.0
    if _eq(gt.get("final_payment_date"), ex.get("final_payment_date")):
        score += 2.0

    for field_name, weight in (
        ("monthly_cost", 3.0),
        ("outstanding", 4.0),
        ("interest_rate", 2.0),
    ):
        g = gt.get(field_name)
        e = ex.get(field_name)
        if _is_number(g) and _is_number(e):
            gtf = float(g)
            exf = float(e)
            tol = max(abs(gtf) * float(numeric_rel_tol), 1e-9)
            if abs(exf - gtf) <= tol:
                score += weight
            else:
                denom = max(abs(gtf), 1.0)
                score += max(0.0, 0.5 - abs(exf - gtf) / denom)

    return score


def _protection_policy_pair_score(
    *,
    gt: Dict[str, Any],
    ex: Dict[str, Any],
    numeric_rel_tol: float,
) -> float:
    score = 0.0

    def _eq(a: Any, b: Any) -> bool:
        return _norm_str(a).lower() == _norm_str(b).lower()

    if _eq(gt.get("owner"), ex.get("owner")):
        score += 3.0
    if _eq(gt.get("policy_type"), ex.get("policy_type")):
        score += 4.0
    if _eq(gt.get("assured_until"), ex.get("assured_until")):
        score += 2.0

    for field_name, weight in (
        ("monthly_cost", 2.0),
        ("amount_assured", 4.0),
    ):
        g = gt.get(field_name)
        e = ex.get(field_name)
        if _is_number(g) and _is_number(e):
            gtf = float(g)
            exf = float(e)
            tol = max(abs(gtf) * float(numeric_rel_tol), 1e-9)
            if abs(exf - gtf) <= tol:
                score += weight
            else:
                denom = max(abs(gtf), 1.0)
                score += max(0.0, 0.5 - abs(exf - gtf) / denom)

    return score


def _people_pair_score(
    *,
    gt: Dict[str, Any],
    ex: Dict[str, Any],
    numeric_rel_tol: float,
) -> float:
    score = 0.0

    def _eq(a: Any, b: Any) -> bool:
        return _norm_str(a).lower() == _norm_str(b).lower()

    if gt.get("client_no") is not None and ex.get("client_no") is not None:
        if gt.get("client_no") == ex.get("client_no"):
            score += 6.0

    if _eq(gt.get("role"), ex.get("role")):
        score += 4.0
    if _eq(gt.get("employment_status"), ex.get("employment_status")):
        score += 2.0
    if _eq(gt.get("occupation_group"), ex.get("occupation_group")):
        score += 1.0
    if _eq(gt.get("first_name"), ex.get("first_name")):
        score += 1.0

    g = gt.get("gross_annual_income")
    e = ex.get("gross_annual_income")
    if _is_number(g) and _is_number(e):
        gtf = float(g)
        exf = float(e)
        tol = max(abs(gtf) * float(numeric_rel_tol), 1e-9)
        if abs(exf - gtf) <= tol:
            score += 5.0
        else:
            denom = max(abs(gtf), 1.0)
            score += max(0.0, 0.5 - abs(exf - gtf) / denom)

    return score


def _pair_records_by_content_generic(
    *,
    gt_records: List[Dict[str, Any]],
    ex_records: List[Dict[str, Any]],
    pk: str,
    numeric_rel_tol: float,
    score_fn,
    min_score: float,
) -> List[Tuple[Optional[Dict[str, Any]], Optional[Dict[str, Any]], str]]:
    if not gt_records and not ex_records:
        return []

    candidates: List[Tuple[float, int, int]] = []
    for i, g in enumerate(gt_records):
        if not isinstance(g, dict):
            continue
        for j, e in enumerate(ex_records):
            if not isinstance(e, dict):
                continue
            candidates.append((score_fn(gt=g, ex=e, numeric_rel_tol=numeric_rel_tol), i, j))

    candidates.sort(key=lambda t: (-t[0], t[1], t[2]))

    used_gt: set[int] = set()
    used_ex: set[int] = set()
    pairs: List[Tuple[Optional[Dict[str, Any]], Optional[Dict[str, Any]], str]] = []

    for score, i, j in candidates:
        if score < min_score:
            break
        if i in used_gt or j in used_ex:
            continue
        used_gt.add(i)
        used_ex.add(j)
        gt = gt_records[i]
        ex = ex_records[j]
        key = _norm_str((gt or {}).get(pk)) or _norm_str((ex or {}).get(pk)) or str(i)
        pairs.append((gt, ex, key))

    for i, gt in enumerate(gt_records):
        if i in used_gt:
            continue
        key = _norm_str((gt or {}).get(pk)) or str(i)
        pairs.append((gt, None, key))

    for j, ex in enumerate(ex_records):
        if j in used_ex:
            continue
        key = _norm_str((ex or {}).get(pk)) or str(j)
        pairs.append((None, ex, key))

    pairs.sort(key=lambda t: _norm_str(t[2]))
    return pairs


def _pair_records_by_content_assets(
    *,
    gt_records: List[Dict[str, Any]],
    ex_records: List[Dict[str, Any]],
    pk: str,
    numeric_rel_tol: float,
) -> List[Tuple[Optional[Dict[str, Any]], Optional[Dict[str, Any]], str]]:
    return _pair_records_by_content_generic(
        gt_records=gt_records,
        ex_records=ex_records,
        pk=pk,
        numeric_rel_tol=numeric_rel_tol,
        score_fn=_asset_pair_score,
        min_score=5.0,
    )


def _pair_records_by_content_income_lines(
    *,
    gt_records: List[Dict[str, Any]],
    ex_records: List[Dict[str, Any]],
    pk: str,
    numeric_rel_tol: float,
) -> List[Tuple[Optional[Dict[str, Any]], Optional[Dict[str, Any]], str]]:
    return _pair_records_by_content_generic(
        gt_records=gt_records,
        ex_records=ex_records,
        pk=pk,
        numeric_rel_tol=numeric_rel_tol,
        score_fn=_income_line_pair_score,
        min_score=4.0,
    )


def _pair_records(
    *,
    gt_records: List[Dict[str, Any]],
    ex_records: List[Dict[str, Any]],
    pk: str,
    entity: str = "",
    numeric_rel_tol: float = 0.01,
) -> List[Tuple[Optional[Dict[str, Any]], Optional[Dict[str, Any]], str]]:
    """Return list of (gt, ex, key) pairs."""


    if entity == "income_lines" and _truthy_env("PAIR_INCOME_LINES_BY_CONTENT", default=True):
        return _pair_records_by_content_income_lines(
            gt_records=gt_records,
            ex_records=ex_records,
            pk=pk,
            numeric_rel_tol=numeric_rel_tol,
        )

    if entity == "people" and _truthy_env("PAIR_PEOPLE_BY_CONTENT", default=True):
        return _pair_records_by_content_generic(
            gt_records=gt_records,
            ex_records=ex_records,
            pk=pk,
            numeric_rel_tol=numeric_rel_tol,
            score_fn=_people_pair_score,
            min_score=6.0,
        )

    if entity == "assets" and _truthy_env("PAIR_ASSETS_BY_CONTENT", default=True):
        return _pair_records_by_content_assets(
            gt_records=gt_records,
            ex_records=ex_records,
            pk=pk,
            numeric_rel_tol=numeric_rel_tol,
        )

    if entity == "liabilities" and _truthy_env("PAIR_LIABILITIES_BY_CONTENT", default=True):
        return _pair_records_by_content_generic(
            gt_records=gt_records,
            ex_records=ex_records,
            pk=pk,
            numeric_rel_tol=numeric_rel_tol,
            score_fn=_liability_pair_score,
            min_score=4.0,
        )

    if entity == "protection_policies" and (
        _truthy_env("PAIR_PROTECTION_POLICIES_BY_CONTENT", default=False)
        or _truthy_env("PAIR_POLICIES_BY_CONTENT", default=True)
    ):
        return _pair_records_by_content_generic(
            gt_records=gt_records,
            ex_records=ex_records,
            pk=pk,
            numeric_rel_tol=numeric_rel_tol,
            score_fn=_protection_policy_pair_score,
            min_score=4.0,
        )

    gt_by_pk = _index_records_by_pk(gt_records, pk)
    ex_by_pk = _index_records_by_pk(ex_records, pk)

    if gt_by_pk and ex_by_pk:
        keys = sorted(set(gt_by_pk.keys()) | set(ex_by_pk.keys()))
        return [(gt_by_pk.get(k), ex_by_pk.get(k), k) for k in keys]

    # If no PKs, fall back to index heuristics.
    if len(gt_records) == 1 and len(ex_records) == 1:
        return [(gt_records[0], ex_records[0], "0")]

    n = max(len(gt_records), len(ex_records))
    pairs: List[Tuple[Optional[Dict[str, Any]], Optional[Dict[str, Any]], str]] = []
    for i in range(n):
        gt = gt_records[i] if i < len(gt_records) else None
        ex = ex_records[i] if i < len(ex_records) else None
        pairs.append((gt, ex, str(i)))
    return pairs


def merge_and_score_one(
    *,
    schema: DataSchema,
    household_id: str,
    dialog_id: str,
    dialog_text: str,
    profile: Dict[str, Any],
    extracted: Dict[str, Any],
    numeric_rel_tol: float,
    include_ids: bool,
    scoring_exclusions: set[str],
    ground_truth_is_grounded: bool,
) -> Dict[str, Any]:
    # Normalize both sides (categoricals + primary key formats) to improve
    # record pairing and reduce trivial string mismatches.
    profile = normalize_profile_values(schema=schema, household_id=household_id, profile=profile)
    extracted = normalize_profile_values(schema=schema, household_id=household_id, profile=extracted)

    entities_out: Dict[str, Any] = {}

    grounded = bool(ground_truth_is_grounded) or bool(profile.get("_ground_truth_is_grounded"))

    matched_fields = 0
    total_fields = 0

    # Stable order
    entity_names = [n for n in DEFAULT_ENTITY_ORDER if n in schema.entities]
    entity_names += [n for n in schema.entities.keys() if n not in set(entity_names)]

    for ent_name in entity_names:
        ent = schema.entities[ent_name]
        gt_records = _as_records((profile.get(ent_name) if isinstance(profile, dict) else None))
        ex_records = _as_records(extracted.get(ent_name) if isinstance(extracted, dict) else None)

        pairs = _pair_records(
            gt_records=gt_records,
            ex_records=ex_records,
            pk=ent.primary_key,
            entity=ent_name,
            numeric_rel_tol=numeric_rel_tol,
        )
        recs_out: List[Dict[str, Any]] = []

        for gt_rec, ex_rec, key in pairs:
            fields_map: Dict[str, FieldCell] = {}
            gt_rec = gt_rec or {}
            ex_rec = ex_rec or {}

            for field in ent.fields:
                gt_key_present = bool(field.name in gt_rec)
                gt_v = gt_rec.get(field.name)
                ex_v = ex_rec.get(field.name)
                ok = _values_match(gt=gt_v, ex=ex_v, field=field, numeric_rel_tol=numeric_rel_tol)

                scoreable = should_score_field(
                    entity=ent,
                    field_name=field.name,
                    include_ids=include_ids,
                    exclusions=scoring_exclusions,
                )
                if scoreable and (gt_key_present if grounded else True):
                    total_fields += 1
                    if ok:
                        matched_fields += 1

                fields_map[field.name] = FieldCell(ground_truth=gt_v, extracted=ex_v, match=ok)

            recs_out.append(
                {
                    "_record_key": key,
                    "fields": {
                        k: {
                            "ground_truth": v.ground_truth,
                            "extracted": v.extracted,
                            "match": v.match,
                            "_gt_key_present": bool(k in gt_rec),
                        }
                        for k, v in fields_map.items()
                    },
                }
            )

        entities_out[ent_name] = recs_out

    fraction = (matched_fields / total_fields) if total_fields else None

    return {
        "household_id": household_id,
        "dialog_id": dialog_id,
        "dialog": dialog_text,
        "ground_truth_is_grounded": grounded,
        "entities": entities_out,
        "accuracy": {
            "matched_fields": matched_fields,
            "total_fields": total_fields,
            "fraction": fraction,
            "numeric_rel_tol": numeric_rel_tol,
            "include_ids": include_ids,
            "ground_truth_is_grounded": grounded,
        },
    }


def _plot_hist(fractions: List[float], out_path: Path) -> None:
    if plt is None:
        return
    out_path.parent.mkdir(parents=True, exist_ok=True)
    plt.figure(figsize=(10, 6))
    plt.hist(fractions, bins=40, range=(0.0, 1.0))
    plt.title("Share of correctly extracted fields per household")
    plt.xlabel("Correct fields / total scored fields")
    plt.ylabel("Households")
    plt.tight_layout()
    plt.savefig(out_path)
    plt.close()


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
        help="Path to ground_truth_pairs.jsonl (default: artifacts/ground_truth_pairs.jsonl)",
    )
    ap.add_argument(
        "--extracted-dir",
        default=str(Path("artifacts").joinpath("extracted")),
        help="Directory with *.extracted.json (default: artifacts/extracted)",
    )
    ap.add_argument(
        "--out-jsonl",
        default=str(Path("artifacts").joinpath("merged", "merged_ground_truth_extracted.jsonl")),
        help="Output merged JSONL (default: artifacts/merged/merged_ground_truth_extracted.jsonl)",
    )
    ap.add_argument(
        "--hist-path",
        default=str(Path("artifacts").joinpath("figures", "extraction_accuracy_hist.png")),
        help="Histogram output path (default: artifacts/figures/extraction_accuracy_hist.png)",
    )
    ap.add_argument(
        "--numeric-rel-tol",
        type=float,
        default=0.01,
        help="Relative tolerance for numeric fields (default: 0.01 = 1%%)",
    )
    ap.add_argument(
        "--limit",
        type=int,
        default=0,
        help="Limit number of households evaluated (0 = all)",
    )
    ap.add_argument(
        "--include-ids",
        action="store_true",
        help="If set, include *_id and primary key fields in scoring denominator",
    )
    ap.add_argument(
        "--scoring-exclusions",
        default=str(default_exclusions_path()),
        help="JSON file with exclude_field_paths[] to omit from scoring",
    )

    args = ap.parse_args()

    schema = DataSchema.load(Path(args.schema))
    pairs_path = Path(args.pairs)
    extracted_dir = Path(args.extracted_dir)
    scoring_exclusions = load_exclusions(Path(args.scoring_exclusions))

    if not pairs_path.exists():
        raise SystemExit(f"Missing pairs file: {pairs_path}")

    extracted_cache: Dict[str, Dict[str, Any]] = {}

    def load_extracted(dialog_id: str) -> Dict[str, Any]:
        if dialog_id in extracted_cache:
            return extracted_cache[dialog_id]
        p = extracted_dir / f"{dialog_id}.extracted.json"
        if not p.exists():
            extracted_cache[dialog_id] = {}
            return {}
        obj = _read_json(p)
        if not isinstance(obj, dict):
            extracted_cache[dialog_id] = {}
            return {}
        extracted_cache[dialog_id] = obj
        return obj

    merged_rows: List[Dict[str, Any]] = []
    fractions: List[float] = []

    seen = 0
    for row in _iter_jsonl(pairs_path):
        hh_id = str(row.get("household_id") or "").strip()
        dialog_id = str(row.get("dialog_id") or "").strip()
        dialog_text = str(row.get("dialog") or "")
        profile = row.get("profile")
        grounded_flag = bool(row.get("ground_truth_is_grounded"))
        if not hh_id or not dialog_id or not isinstance(profile, dict):
            continue

        seen += 1
        if args.limit and args.limit > 0 and seen > int(args.limit):
            break

        extracted = load_extracted(dialog_id)

        merged = merge_and_score_one(
            schema=schema,
            household_id=hh_id,
            dialog_id=dialog_id,
            dialog_text=dialog_text,
            profile=profile,
            extracted=extracted,
            numeric_rel_tol=float(args.numeric_rel_tol),
            include_ids=bool(args.include_ids),
            scoring_exclusions=scoring_exclusions,
            ground_truth_is_grounded=grounded_flag,
        )
        merged_rows.append(merged)

        frac = merged.get("accuracy", {}).get("fraction")
        if isinstance(frac, (int, float)):
            fractions.append(float(frac))

    out_jsonl = Path(args.out_jsonl)
    _write_jsonl(out_jsonl, merged_rows)

    if fractions:
        _plot_hist(fractions, Path(args.hist_path))

    report = {
        "pairs": str(pairs_path),
        "extracted_dir": str(extracted_dir),
        "merged_out": str(out_jsonl),
        "hist_path": str(Path(args.hist_path)),
        "households": len(merged_rows),
        "scored_households": len(fractions),
        "numeric_rel_tol": float(args.numeric_rel_tol),
        "include_ids": bool(args.include_ids),
        "mean_fraction": (sum(fractions) / len(fractions)) if fractions else None,
    }

    report_path = out_jsonl.parent / "accuracy_report.json"
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print(json.dumps(report, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
