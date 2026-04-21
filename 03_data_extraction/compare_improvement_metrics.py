from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, Iterable, Tuple

from scoring_config import default_exclusions_path, load_exclusions, should_score_field
from schema_spec import DEFAULT_ENTITY_ORDER, DataSchema


def _iter_jsonl(path: Path) -> Iterable[Dict[str, Any]]:
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            s = line.strip()
            if not s:
                continue
            obj = json.loads(s)
            if isinstance(obj, dict):
                yield obj


def _missing(v: Any) -> bool:
    return v is None or v == ""


def _summarize(
    *,
    merged_jsonl: Path,
    schema: DataSchema,
    scoring_exclusions: set[str],
) -> Dict[str, Any]:
    fractions = []
    entity_metrics: Dict[str, Dict[str, int]] = defaultdict(
        lambda: {"missing": 0, "error": 0, "extra": 0, "total": 0}
    )
    field_metrics: Dict[Tuple[str, str], Dict[str, int]] = defaultdict(
        lambda: {"missing": 0, "error": 0, "extra": 0, "total": 0}
    )

    for row in _iter_jsonl(merged_jsonl):
        acc = row.get("accuracy")
        if isinstance(acc, dict) and isinstance(acc.get("fraction"), (int, float)):
            fractions.append(float(acc["fraction"]))

        grounded = bool(row.get("ground_truth_is_grounded"))
        entities = row.get("entities")
        if not isinstance(entities, dict):
            continue

        for entity_name, records in entities.items():
            entity = schema.entities.get(entity_name)
            if entity is None or not isinstance(records, list):
                continue
            for rec in records:
                if not isinstance(rec, dict):
                    continue
                fields = rec.get("fields")
                if not isinstance(fields, dict):
                    continue
                for field in entity.fields:
                    if not should_score_field(
                        entity=entity,
                        field_name=field.name,
                        include_ids=False,
                        exclusions=scoring_exclusions,
                    ):
                        continue
                    cell = fields.get(field.name)
                    if not isinstance(cell, dict):
                        continue
                    gt_present = bool(cell.get("_gt_key_present"))
                    if grounded and not gt_present:
                        continue

                    gt = cell.get("ground_truth")
                    ex = cell.get("extracted")
                    match = bool(cell.get("match"))
                    entity_metrics[entity_name]["total"] += 1
                    field_metrics[(entity_name, field.name)]["total"] += 1
                    if match:
                        continue
                    if not _missing(gt) and _missing(ex):
                        bucket = "missing"
                    elif _missing(gt) and not _missing(ex):
                        bucket = "extra"
                    else:
                        bucket = "error"
                    entity_metrics[entity_name][bucket] += 1
                    field_metrics[(entity_name, field.name)][bucket] += 1

    n = len(fractions)
    overall = {
        "dialogs": n,
        "dialogs_100": sum(1 for x in fractions if x >= 1.0),
        "dialogs_95": sum(1 for x in fractions if x >= 0.95),
        "dialogs_90": sum(1 for x in fractions if x >= 0.90),
        "mean_fraction": (sum(fractions) / n) if n else None,
    }
    return {
        "overall": overall,
        "entities": {k: dict(v) for k, v in entity_metrics.items()},
        "fields": {f"{k[0]}.{k[1]}": dict(v) for k, v in field_metrics.items()},
    }


def _rate(n: int, d: int) -> float:
    return (n / d) if d else 0.0


def _fmt_rate(x: float) -> str:
    return f"{x:.3f}"


def _fmt_delta(x: float) -> str:
    sign = "+" if x >= 0 else ""
    return f"{sign}{x:.3f}"


def _markdown_table(rows: list[list[Any]], headers: list[str]) -> str:
    widths = [len(h) for h in headers]
    for row in rows:
        for i, val in enumerate(row):
            widths[i] = max(widths[i], len(str(val)))
    out = []
    out.append("| " + " | ".join(headers[i].ljust(widths[i]) for i in range(len(headers))) + " |")
    out.append("|-" + "-|-".join("-" * w for w in widths) + "-|")
    for row in rows:
        out.append("| " + " | ".join(str(row[i]).ljust(widths[i]) for i in range(len(headers))) + " |")
    return "\n".join(out)


def _write_report(out_md: Path, dataset_name: str, baseline: Dict[str, Any], improved: Dict[str, Any]) -> None:
    b = baseline["overall"]
    i = improved["overall"]
    n = int(i["dialogs"] or b["dialogs"] or 0)
    overall_rows = []
    for key, label in (
        ("dialogs_100", "Dialogs with 100% correct fields"),
        ("dialogs_95", "Dialogs with >=95% correct fields"),
        ("dialogs_90", "Dialogs with >=90% correct fields"),
    ):
        b_rate = _rate(int(b[key]), int(b["dialogs"]))
        i_rate = _rate(int(i[key]), int(i["dialogs"]))
        overall_rows.append([label, f"{b[key]}/{b['dialogs']} = {_fmt_rate(b_rate)}", f"{i[key]}/{i['dialogs']} = {_fmt_rate(i_rate)}", _fmt_delta(i_rate - b_rate)])
    if b.get("mean_fraction") is not None and i.get("mean_fraction") is not None:
        overall_rows.append(["Mean dialog field accuracy", _fmt_rate(float(b["mean_fraction"])), _fmt_rate(float(i["mean_fraction"])), _fmt_delta(float(i["mean_fraction"]) - float(b["mean_fraction"]))])

    entity_rows = []
    for entity in DEFAULT_ENTITY_ORDER:
        be = baseline["entities"].get(entity, {"missing": 0, "error": 0, "extra": 0, "total": 0})
        ie = improved["entities"].get(entity, {"missing": 0, "error": 0, "extra": 0, "total": 0})
        total = int(ie.get("total") or be.get("total") or 0)
        for bucket, label in (("missing", "Missing"), ("error", "Errors"), ("extra", "Invented")):
            b_rate = _rate(int(be.get(bucket, 0)), int(be.get("total", 0)))
            i_rate = _rate(int(ie.get(bucket, 0)), int(ie.get("total", 0)))
            entity_rows.append([entity, label, f"{b_rate:.1%}", f"{i_rate:.1%}", f"{(i_rate - b_rate):+.1%}", total])

    out_md.parent.mkdir(parents=True, exist_ok=True)
    out_md.write_text(
        "\n".join(
            [
                f"# Improvement delta: {dataset_name}",
                "",
                "Baseline is the original extraction output. Improved applies the asset rescue overwrite pass before scoring.",
                "",
                "## Overall metrics",
                "",
                _markdown_table(overall_rows, ["Metric", "Baseline", "Improved", "Delta"]),
                "",
                "## Per-entity error-rate metrics",
                "",
                _markdown_table(entity_rows, ["Entity", "Metric", "Baseline", "Improved", "Delta", "Total cells"]),
                "",
            ]
        ),
        encoding="utf-8",
    )


def main() -> int:
    ap = argparse.ArgumentParser(description="Compare baseline and improved extraction metrics.")
    ap.add_argument("--baseline-merged", required=True)
    ap.add_argument("--improved-merged", required=True)
    ap.add_argument("--out-json", required=True)
    ap.add_argument("--out-md", required=True)
    ap.add_argument("--dataset-name", default="dataset")
    ap.add_argument(
        "--schema",
        default=str(Path("..").joinpath("01_data_generation", "config", "schema.json")),
    )
    ap.add_argument(
        "--scoring-exclusions",
        default=str(default_exclusions_path()),
    )
    args = ap.parse_args()

    schema = DataSchema.load(Path(args.schema))
    scoring_exclusions = load_exclusions(Path(args.scoring_exclusions))
    baseline = _summarize(
        merged_jsonl=Path(args.baseline_merged),
        schema=schema,
        scoring_exclusions=scoring_exclusions,
    )
    improved = _summarize(
        merged_jsonl=Path(args.improved_merged),
        schema=schema,
        scoring_exclusions=scoring_exclusions,
    )
    out = {"dataset": args.dataset_name, "baseline": baseline, "improved": improved}
    out_json = Path(args.out_json)
    out_json.parent.mkdir(parents=True, exist_ok=True)
    out_json.write_text(json.dumps(out, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    _write_report(Path(args.out_md), args.dataset_name, baseline, improved)
    print(json.dumps({"out_json": args.out_json, "out_md": args.out_md}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
