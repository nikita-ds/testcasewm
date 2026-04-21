from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

import pandas as pd

from schema_spec import DataSchema, EntitySpec, FieldSpec
from scoring_config import default_exclusions_path, load_exclusions, should_score_field


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _iter_jsonl(path: Path) -> Iterable[Dict[str, Any]]:
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            s = line.strip()
            if not s:
                continue
            obj = json.loads(s)
            if isinstance(obj, dict):
                yield obj


def _as_records(v: Any) -> List[Dict[str, Any]]:
    if v is None:
        return []
    if isinstance(v, list):
        return [x for x in v if isinstance(x, dict)]
    if isinstance(v, dict):
        return [v]
    return []


def _is_missing_record_side(field_cells: Dict[str, Any], side: str) -> bool:
    """Return True if all values for `side` are None for this record.

    side: 'ground_truth' or 'extracted'
    """

    for v in field_cells.values():
        if not isinstance(v, dict):
            continue
        if v.get(side) is not None:
            return False
    return True


def _fmt_value(v: Any) -> str:
    if v is None:
        return ""
    if isinstance(v, float):
        # keep stable-ish formatting for grouping
        return f"{v:.6g}"
    return str(v)


@dataclass(frozen=True)
class RecordPairStats:
    household_id: str
    entity: str
    record_key: str
    gt_missing: bool
    ex_missing: bool
    status: str


def _plot_worst_fields(field_stats: pd.DataFrame, out_path: Path, top_n: int = 25) -> None:
    worst = field_stats.sort_values(["match_rate", "n_total"], ascending=[True, False]).head(top_n)
    if worst.empty:
        return

    labels = (worst["entity"] + "." + worst["field"]).tolist()
    values = (1.0 - worst["match_rate"]).tolist()

    plt.figure(figsize=(12, 8))
    plt.barh(list(reversed(labels)), list(reversed(values)))
    plt.title(f"Worst fields by mismatch rate (top {min(top_n, len(worst))})")
    plt.xlabel("Mismatch rate")
    plt.tight_layout()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    plt.savefig(out_path)
    plt.close()


def _plot_error_type_breakdown(field_stats: pd.DataFrame, out_path: Path, top_n: int = 15) -> None:
    top = field_stats.copy()
    top["n_errors"] = top["n_total"] - top["n_match"]
    top = top.sort_values(["n_errors", "n_total"], ascending=[False, False]).head(top_n)
    if top.empty:
        return

    labels = (top["entity"] + "." + top["field"]).tolist()
    missing_ex = top["n_missing_extracted"].tolist()
    extra_ex = top["n_extra_extracted"].tolist()
    value_mis = top["n_value_mismatch"].tolist()

    y = list(range(len(labels)))

    plt.figure(figsize=(12, 7))
    left = [0] * len(labels)

    plt.barh(y, missing_ex, left=left, label="Missing extracted")
    left = [l + v for l, v in zip(left, missing_ex)]

    plt.barh(y, extra_ex, left=left, label="Extra extracted")
    left = [l + v for l, v in zip(left, extra_ex)]

    plt.barh(y, value_mis, left=left, label="Value mismatch")

    plt.yticks(y, labels)
    plt.title(f"Error type breakdown (top {min(top_n, len(top))} fields by errors)")
    plt.xlabel("# cells")
    plt.legend()
    plt.tight_layout()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    plt.savefig(out_path)
    plt.close()


def _plot_record_pairing(entity_pairing: pd.DataFrame, out_path: Path) -> None:
    if entity_pairing.empty:
        return

    df = entity_pairing.set_index("entity")
    entities = df.index.tolist()
    gt_only = df["records_gt_only"].tolist()
    ex_only = df["records_ex_only"].tolist()
    both = df["records_both_present"].tolist()

    y = list(range(len(entities)))
    plt.figure(figsize=(10, 5 + 0.4 * len(entities)))

    left = [0] * len(entities)
    plt.barh(y, gt_only, left=left, label="GT-only records")
    left = [l + v for l, v in zip(left, gt_only)]

    plt.barh(y, ex_only, left=left, label="Extracted-only records")
    left = [l + v for l, v in zip(left, ex_only)]

    plt.barh(y, both, left=left, label="Both present")

    plt.yticks(y, entities)
    plt.title("Record pairing status by entity")
    plt.xlabel("# record pairs")
    plt.legend()
    plt.tight_layout()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    plt.savefig(out_path)
    plt.close()


def _write_markdown_report(
    *,
    out_path: Path,
    summary: Dict[str, Any],
    entity_pairing: pd.DataFrame,
    worst_fields: pd.DataFrame,
    examples: pd.DataFrame,
) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)

    def _md_table(df: pd.DataFrame, cols: List[str], n: int) -> str:
        if df.empty:
            return "(none)"

        d = df[cols].head(n).copy()

        def _cell(x: Any) -> str:
            if x is None:
                return ""
            if isinstance(x, float):
                return f"{x:.6g}"
            s = str(x)
            return s.replace("\n", " ").replace("|", "\\|")

        header = "| " + " | ".join(cols) + " |"
        sep = "| " + " | ".join(["---"] * len(cols)) + " |"
        rows = []
        for _, r in d.iterrows():
            rows.append("| " + " | ".join(_cell(r[c]) for c in cols) + " |")
        return "\n".join([header, sep] + rows)

    lines: List[str] = []
    lines.append("# Extraction discrepancy analysis\n")

    lines.append("## Overall\n")
    lines.append(f"- Households analyzed: **{summary.get('n_households', 0)}**")
    lines.append(f"- Scored cells: **{summary.get('n_scored_cells', 0)}**")
    lines.append(f"- Match rate (cells): **{summary.get('match_rate', 0.0):.3f}**")
    lines.append("\n### Error breakdown (scored cells)\n")
    lines.append(f"- Missing extracted: **{summary.get('n_missing_extracted', 0)}**")
    lines.append(f"- Extra extracted: **{summary.get('n_extra_extracted', 0)}**")
    lines.append(f"- Value mismatch: **{summary.get('n_value_mismatch', 0)}**")
    lines.append("")

    lines.append("## Record pairing by entity\n")
    if entity_pairing.empty:
        lines.append("(none)\n")
    else:
        cols = [
            "entity",
            "record_pairs",
            "records_both_present",
            "records_gt_only",
            "records_ex_only",
            "both_present_rate",
            "sample_gt_only_keys",
            "sample_ex_only_keys",
        ]
        lines.append(_md_table(entity_pairing, cols=cols, n=9999))
        lines.append("")

    lines.append("## Worst fields (by match rate)\n")
    lines.append(_md_table(
        worst_fields,
        cols=[
            "entity",
            "field",
            "field_type",
            "n_total",
            "match_rate",
            "n_missing_extracted",
            "n_extra_extracted",
            "n_value_mismatch",
        ],
        n=25,
    ))
    lines.append("")

    # Missing extracted attribution
    lines.append("## Missing extracted: why?\n")
    lines.append(
        "Missing extracted happens for two different reasons: (a) **record pairing failed** (GT record exists but no extracted record matched its primary key), and (b) **within a paired record**, extracted left a specific field empty."
    )
    lines.append("")

    if not worst_fields.empty and "n_missing_extracted_gt_only" in worst_fields.columns:
        miss = worst_fields.copy()
        miss["missing_total"] = miss["n_missing_extracted"]
        miss_gt_only = miss.sort_values(["n_missing_extracted_gt_only", "missing_total"], ascending=[False, False])
        miss_within = miss.sort_values(["n_missing_extracted_within_paired", "missing_total"], ascending=[False, False])

        lines.append("### Top missing due to unpaired records (gt_only)\n")
        lines.append(
            _md_table(
                miss_gt_only,
                cols=[
                    "entity",
                    "field",
                    "field_type",
                    "n_total",
                    "n_missing_extracted_gt_only",
                    "n_missing_extracted",
                ],
                n=20,
            )
        )
        lines.append("")

        lines.append("### Top missing within paired records (both)\n")
        lines.append(
            _md_table(
                miss_within,
                cols=[
                    "entity",
                    "field",
                    "field_type",
                    "n_total",
                    "n_missing_extracted_within_paired",
                    "n_missing_extracted",
                ],
                n=20,
            )
        )
        lines.append("")

    lines.append("## Common mismatch examples\n")
    lines.append(_md_table(
        examples,
        cols=["entity", "field", "ground_truth", "extracted", "count"],
        n=40,
    ))
    lines.append("")

    out_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    ap = argparse.ArgumentParser(description="Analyze field-level extraction discrepancies from merged JSONL")
    ap.add_argument(
        "--merged-jsonl",
        default=str(Path(__file__).resolve().parents[1] / "artifacts" / "merged" / "merged_ground_truth_extracted.jsonl"),
        help="Path to merged_ground_truth_extracted.jsonl",
    )
    ap.add_argument(
        "--out-dir",
        default=str(Path(__file__).resolve().parents[1] / "artifacts"),
        help="Base artifacts dir (default: 03_data_extraction/artifacts)",
    )
    ap.add_argument("--include-ids", action="store_true", help="Include ID fields in scoring/analysis")
    ap.add_argument(
        "--scoring-exclusions",
        default=str(default_exclusions_path()),
        help="JSON file with exclude_field_paths[] to omit from scoring",
    )
    ap.add_argument(
        "--print-value-mismatches",
        action="store_true",
        help="Print a sample of value mismatches (ground_truth vs extracted) to stdout",
    )
    ap.add_argument(
        "--print-limit",
        type=int,
        default=30,
        help="Max number of value mismatch rows to print (default: 30)",
    )

    args = ap.parse_args()

    merged_path = Path(args.merged_jsonl)
    out_dir = Path(args.out_dir)

    schema_path = _repo_root() / "01_data_generation" / "config" / "schema.json"
    schema = DataSchema.load(schema_path)

    include_ids = bool(args.include_ids)
    scoring_exclusions = load_exclusions(Path(args.scoring_exclusions))

    flat_rows: List[Dict[str, Any]] = []
    record_pairs: List[RecordPairStats] = []

    household_ids: set[str] = set()

    for obj in _iter_jsonl(merged_path):
        hh = str(obj.get("household_id") or "").strip()
        if not hh:
            continue
        household_ids.add(hh)

        grounded = bool(obj.get("ground_truth_is_grounded"))

        entities = obj.get("entities")
        if not isinstance(entities, dict):
            continue

        for ent_name, recs_any in entities.items():
            if ent_name not in schema.entities:
                continue
            ent = schema.entities[ent_name]

            recs = _as_records(recs_any)
            for rec in recs:
                record_key = str(rec.get("_record_key") or "").strip()
                fields = rec.get("fields")
                if not isinstance(fields, dict):
                    continue

                gt_missing = _is_missing_record_side(fields, "ground_truth")
                ex_missing = _is_missing_record_side(fields, "extracted")

                if gt_missing and ex_missing:
                    status = "both_missing"
                elif gt_missing and not ex_missing:
                    status = "ex_only"
                elif (not gt_missing) and ex_missing:
                    status = "gt_only"
                else:
                    status = "both"

                record_pairs.append(
                    RecordPairStats(
                        household_id=hh,
                        entity=ent_name,
                        record_key=record_key,
                        gt_missing=gt_missing,
                        ex_missing=ex_missing,
                        status=status,
                    )
                )

                for field_name, cell in fields.items():
                    if not isinstance(cell, dict):
                        continue
                    gt = cell.get("ground_truth")
                    ex = cell.get("extracted")
                    match = bool(cell.get("match"))

                    gt_key_present = bool(cell.get("_gt_key_present")) if grounded else True

                    field_spec: Optional[FieldSpec] = None
                    for f in ent.fields:
                        if f.name == field_name:
                            field_spec = f
                            break

                    scoreable = should_score_field(
                        entity=ent,
                        field_name=field_name,
                        include_ids=include_ids,
                        exclusions=scoring_exclusions,
                    ) and (gt_key_present if grounded else True)

                    expected = gt_key_present if grounded else (gt is not None)

                    flat_rows.append(
                        {
                            "household_id": hh,
                            "entity": ent_name,
                            "record_key": record_key,
                            "record_status": status,
                            "field": field_name,
                            "field_type": (str(field_spec.type) if field_spec else ""),
                            "ground_truth": gt,
                            "extracted": ex,
                            "match": match,
                            "scoreable": scoreable,
                            "ground_truth_is_grounded": grounded,
                            "gt_key_present": gt_key_present,
                            "expected": expected,
                            "gt_present": gt is not None,
                            "ex_present": ex is not None,
                            "gt_missing_record": gt_missing,
                            "ex_missing_record": ex_missing,
                        }
                    )

    df = pd.DataFrame(flat_rows)
    if df.empty:
        raise SystemExit(f"No rows parsed from {merged_path}")

    df_scored = df[df["scoreable"]].copy()

    # Overall summary
    n_scored = int(len(df_scored))
    n_match = int(df_scored["match"].sum()) if n_scored else 0

    missing_ex = int(((df_scored["expected"]) & (df_scored["gt_present"]) & (~df_scored["ex_present"])).sum())
    extra_ex = int(((~df_scored["expected"]) & (df_scored["ex_present"])).sum())
    value_mis = int(((df_scored["expected"]) & (df_scored["ex_present"]) & (~df_scored["match"])).sum())

    summary = {
        "n_households": len(household_ids),
        "n_scored_cells": n_scored,
        "n_matched_cells": n_match,
        "match_rate": (n_match / n_scored) if n_scored else 0.0,
        "n_missing_extracted": missing_ex,
        "n_extra_extracted": extra_ex,
        "n_value_mismatch": value_mis,
        "include_ids": include_ids,
    }

    # Per-field stats
    def _agg_field(g: pd.DataFrame) -> pd.Series:
        n_total = len(g)
        n_match_local = int(g["match"].sum())
        n_missing_ex_local = int(((g["expected"]) & (g["gt_present"]) & (~g["ex_present"])).sum())
        n_extra_ex_local = int(((~g["expected"]) & (g["ex_present"])).sum())
        n_value_mis_local = int(((g["expected"]) & (g["ex_present"]) & (~g["match"])).sum())

        # Attribute missing/extra to record pairing vs within-pair failures.
        n_missing_ex_gt_only = int(
            (((g["expected"]) & (g["gt_present"]) & (~g["ex_present"])) & (g["record_status"] == "gt_only")).sum()
        )
        n_missing_ex_within = int(
            (((g["expected"]) & (g["gt_present"]) & (~g["ex_present"])) & (g["record_status"] == "both")).sum()
        )
        n_extra_ex_ex_only = int(
            (((~g["expected"]) & (g["ex_present"])) & (g["record_status"] == "ex_only")).sum()
        )
        n_extra_ex_within = int(
            (((~g["expected"]) & (g["ex_present"])) & (g["record_status"] == "both")).sum()
        )

        field_type = str(g["field_type"].iloc[0] or "")

        return pd.Series(
            {
                "field_type": field_type,
                "n_total": int(n_total),
                "n_match": int(n_match_local),
                "match_rate": (n_match_local / n_total) if n_total else 0.0,
                "n_missing_extracted": int(n_missing_ex_local),
                "n_missing_extracted_gt_only": int(n_missing_ex_gt_only),
                "n_missing_extracted_within_paired": int(n_missing_ex_within),
                "n_extra_extracted": int(n_extra_ex_local),
                "n_extra_extracted_ex_only": int(n_extra_ex_ex_only),
                "n_extra_extracted_within_paired": int(n_extra_ex_within),
                "n_value_mismatch": int(n_value_mis_local),
            }
        )

    field_stats = (
        df_scored.groupby(["entity", "field"], dropna=False)
        .apply(_agg_field)
        .reset_index()
        .sort_values(["match_rate", "n_total"], ascending=[True, False])
    )

    # Per-entity record pairing summary
    rp = pd.DataFrame([r.__dict__ for r in record_pairs])
    if rp.empty:
        entity_pairing = pd.DataFrame(columns=[
            "entity",
            "record_pairs",
            "records_both_present",
            "records_gt_only",
            "records_ex_only",
            "records_both_missing",
            "both_present_rate",
            "sample_gt_only_keys",
            "sample_ex_only_keys",
        ])
    else:
        def _pairing_agg(g: pd.DataFrame) -> pd.Series:
            both = int((~g["gt_missing"] & ~g["ex_missing"]).sum())
            gt_only = int((~g["gt_missing"] & g["ex_missing"]).sum())
            ex_only = int((g["gt_missing"] & ~g["ex_missing"]).sum())
            both_missing = int((g["gt_missing"] & g["ex_missing"]).sum())
            total = int(len(g))

            sample_gt = (
                g.loc[(~g["gt_missing"]) & (g["ex_missing"]), "record_key"].dropna().astype(str).head(5).tolist()
            )
            sample_ex = (
                g.loc[(g["gt_missing"]) & (~g["ex_missing"]), "record_key"].dropna().astype(str).head(5).tolist()
            )

            return pd.Series(
                {
                    "record_pairs": total,
                    "records_both_present": both,
                    "records_gt_only": gt_only,
                    "records_ex_only": ex_only,
                    "records_both_missing": both_missing,
                    "both_present_rate": (both / total) if total else 0.0,
                    "sample_gt_only_keys": ",".join(sample_gt),
                    "sample_ex_only_keys": ",".join(sample_ex),
                }
            )

        entity_pairing = (
            rp.groupby(["entity"], dropna=False)
            .apply(_pairing_agg)
            .reset_index()
            .sort_values(["both_present_rate", "record_pairs"], ascending=[True, False])
        )

    # Missing/extra samples for debugging
    missing_cells = df_scored[(df_scored["expected"]) & (df_scored["gt_present"]) & (~df_scored["ex_present"])].copy()
    extra_cells = df_scored[(~df_scored["expected"]) & (df_scored["ex_present"])].copy()

    def _prep_cells(cells: pd.DataFrame) -> pd.DataFrame:
        if cells.empty:
            return pd.DataFrame(
                columns=[
                    "household_id",
                    "entity",
                    "record_key",
                    "record_status",
                    "field",
                    "field_type",
                    "ground_truth",
                    "extracted",
                ]
            )
        out = cells[[
            "household_id",
            "entity",
            "record_key",
            "record_status",
            "field",
            "field_type",
            "ground_truth",
            "extracted",
        ]].copy()
        out["ground_truth"] = out["ground_truth"].map(_fmt_value)
        out["extracted"] = out["extracted"].map(_fmt_value)
        return out

    # Common mismatch examples (value mismatches only, to avoid record-alignment noise)
    ex_df = df_scored[(df_scored["expected"]) & (df_scored["ex_present"]) & (~df_scored["match"])].copy()
    if ex_df.empty:
        examples = pd.DataFrame(columns=["entity", "field", "ground_truth", "extracted", "count"])
    else:
        ex_df["gt_s"] = ex_df["ground_truth"].map(_fmt_value)
        ex_df["ex_s"] = ex_df["extracted"].map(_fmt_value)
        examples = (
            ex_df.groupby(["entity", "field", "gt_s", "ex_s"], dropna=False)
            .size()
            .reset_index(name="count")
            .rename(columns={"gt_s": "ground_truth", "ex_s": "extracted"})
            .sort_values(["count"], ascending=[False])
        )

    # Write outputs
    (out_dir / "tables").mkdir(parents=True, exist_ok=True)
    (out_dir / "report").mkdir(parents=True, exist_ok=True)
    (out_dir / "figures").mkdir(parents=True, exist_ok=True)

    (out_dir / "discrepancy_summary.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    field_stats.to_csv(out_dir / "tables" / "discrepancy_field_stats.csv", index=False)
    entity_pairing.to_csv(out_dir / "tables" / "discrepancy_entity_record_pairing.csv", index=False)
    examples.head(200).to_csv(out_dir / "tables" / "discrepancy_examples.csv", index=False)

    # Detailed value-mismatch cells (per household/record/field). This is the most
    # actionable view when debugging "value mismatch" errors.
    value_mismatch_cells = df_scored[(df_scored["expected"]) & (df_scored["ex_present"]) & (~df_scored["match"])].copy()
    if value_mismatch_cells.empty:
        value_mismatch_cells_out = pd.DataFrame(
            columns=[
                "household_id",
                "entity",
                "record_key",
                "record_status",
                "field",
                "field_type",
                "ground_truth",
                "extracted",
            ]
        )
    else:
        value_mismatch_cells_out = value_mismatch_cells[[
            "household_id",
            "entity",
            "record_key",
            "record_status",
            "field",
            "field_type",
            "ground_truth",
            "extracted",
        ]].copy()
        value_mismatch_cells_out["ground_truth"] = value_mismatch_cells_out["ground_truth"].map(_fmt_value)
        value_mismatch_cells_out["extracted"] = value_mismatch_cells_out["extracted"].map(_fmt_value)
        value_mismatch_cells_out = value_mismatch_cells_out.sort_values(
            ["entity", "field", "household_id", "record_key"],
            ascending=[True, True, True, True],
        )

    value_mismatch_csv = out_dir / "tables" / "value_mismatch_cells.csv"
    value_mismatch_cells_out.to_csv(value_mismatch_csv, index=False)

    _prep_cells(missing_cells).head(500).to_csv(out_dir / "tables" / "discrepancy_missing_extracted_samples.csv", index=False)
    _prep_cells(extra_cells).head(500).to_csv(out_dir / "tables" / "discrepancy_extra_extracted_samples.csv", index=False)

    if not rp.empty:
        rp[["household_id", "entity", "record_key", "status"]].to_csv(
            out_dir / "tables" / "discrepancy_record_pair_status.csv", index=False
        )

    _plot_worst_fields(field_stats, out_dir / "figures" / "discrepancy_worst_fields.png", top_n=25)
    _plot_error_type_breakdown(field_stats, out_dir / "figures" / "discrepancy_error_type_breakdown.png", top_n=15)
    _plot_record_pairing(entity_pairing, out_dir / "figures" / "discrepancy_record_pairing.png")

    _write_markdown_report(
        out_path=out_dir / "report" / "discrepancy_report.md",
        summary=summary,
        entity_pairing=entity_pairing,
        worst_fields=field_stats,
        examples=examples,
    )

    if bool(args.print_value_mismatches):
        n_total = int(len(value_mismatch_cells_out))
        n_print = int(max(0, args.print_limit or 0))
        print(
            json.dumps(
                {
                    "status": "value_mismatch_sample",
                    "n_total": n_total,
                    "n_print": min(n_print, n_total),
                    "csv": str(value_mismatch_csv),
                },
                ensure_ascii=False,
            )
        )

        if n_print > 0 and n_total > 0:
            for _, r in value_mismatch_cells_out.head(n_print).iterrows():
                print(
                    json.dumps(
                        {
                            "type": "value_mismatch",
                            "household_id": r.get("household_id"),
                            "entity": r.get("entity"),
                            "record_key": r.get("record_key"),
                            "field": r.get("field"),
                            "ground_truth": r.get("ground_truth"),
                            "extracted": r.get("extracted"),
                            "field_type": r.get("field_type"),
                            "record_status": r.get("record_status"),
                        },
                        ensure_ascii=False,
                    )
                )

    print(json.dumps({"status": "ok", "out_dir": str(out_dir)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
