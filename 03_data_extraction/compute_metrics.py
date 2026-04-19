"""
Extraction quality metrics computation module for pipeline results.
"""
import json
import csv
from pathlib import Path
from collections import defaultdict

try:
    from tabulate import tabulate
except Exception:  # pragma: no cover - fallback for local envs
    def tabulate(rows, headers, tablefmt="github"):
        lines = [" | ".join(headers)]
        for row in rows:
            lines.append(" | ".join(str(x) for x in row))
        return "\n".join(lines)

# Input artifact paths
ARTIFACTS = Path(__file__).parent / "artifacts"
MERGED = ARTIFACTS / "merged"
ACCURACY_REPORT = MERGED / "accuracy_report.json"
DISCREPANCY = ARTIFACTS / "discrepancy_summary.json"
FIELD_STATS = ARTIFACTS / "tables" / "discrepancy_field_stats.csv"
RECORD_PAIR_STATUS = ARTIFACTS / "tables" / "discrepancy_record_pair_status.csv"

ENTITY_FIELDS = [
    "people", "liabilities", "protection_policies", "assets", "households", "income_lines"
]

def load_json(path):
    """Load JSON file from path."""
    with open(path, encoding="utf-8") as f:
        return json.load(f)

def load_csv(path):
    """Load CSV file as list of dicts."""
    with open(path, encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def _load_dialog_fractions() -> list[float]:
    if not (MERGED / "merged_ground_truth_extracted.jsonl").exists():
        return []

    vals: list[float] = []
    with open(MERGED / "merged_ground_truth_extracted.jsonl", encoding="utf-8") as f:
        for line in f:
            s = line.strip()
            if not s:
                continue
            row = json.loads(s)
            frac = row.get("fraction")
            if not isinstance(frac, (int, float)):
                acc = row.get("accuracy")
                if isinstance(acc, dict):
                    frac = acc.get("fraction")
            if isinstance(frac, (int, float)):
                vals.append(float(frac))
    return vals

def main():
    # 1. Overall dialog-level metrics
    acc = load_json(ACCURACY_REPORT)
    dialog_stats = acc.get("dialog_stats", [])
    dialog_fractions = []
    if isinstance(dialog_stats, list) and dialog_stats:
        dialog_fractions = [float(d.get("fraction", 0)) for d in dialog_stats if isinstance(d, dict)]
    else:
        dialog_fractions = _load_dialog_fractions()

    n = len(dialog_fractions)
    if n == 0:
        print("No dialogs found in accuracy_report.json. Metrics not computed.")
        table_txt = tabulate([], headers=["Entity", "Missed", "Errors", "Invented", "Total cells"], tablefmt="github")
        out_path = ARTIFACTS / "metrics_table.txt"
        with open(out_path, "w", encoding="utf-8") as f:
            f.write(table_txt)
            f.write("\n")
        return

    n_100 = sum(1 for v in dialog_fractions if v >= 1.0)
    n_95 = sum(1 for v in dialog_fractions if v >= 0.95)
    n_90 = sum(1 for v in dialog_fractions if v >= 0.90)
    print(f"Share of dialogs with 100% correct: {n_100}/{n} = {n_100/n:.3f}")
    print(f"Share of dialogs with ≥95% correct: {n_95}/{n} = {n_95/n:.3f}")
    print(f"Share of dialogs with ≥90% correct: {n_90}/{n} = {n_90/n:.3f}")

    # 2. Per-entity metrics
    field_stats = load_csv(FIELD_STATS)
    entity_metrics = defaultdict(lambda: {"missing": 0, "error": 0, "extra": 0, "total": 0})
    for row in field_stats:
        entity = row["entity"]
        if entity not in ENTITY_FIELDS:
            continue
        entity_metrics[entity]["missing"] += int(row.get("n_missing_extracted") or row.get("missing_extracted") or 0)
        entity_metrics[entity]["error"] += int(row.get("n_value_mismatch") or row.get("value_mismatch") or 0)
        entity_metrics[entity]["extra"] += int(row.get("n_extra_extracted") or row.get("extra_extracted") or 0)
        entity_metrics[entity]["total"] += int(row.get("n_total") or row.get("total_cells") or 0)

    # Build table for output
    table = []
    for entity in ENTITY_FIELDS:
        m = entity_metrics[entity]
        total = m["total"] or 1
        table.append([
            entity,
            f"{m['missing']/total:.1%}",
            f"{m['error']/total:.1%}",
            f"{m['extra']/total:.1%}",
            m["total"]
        ])
    print("\nPer-entity metrics:")
    table_txt = tabulate(
        table,
        headers=["Entity", "Missed", "Errors", "Invented", "Total cells"],
        tablefmt="github"
    )
    print(table_txt)

    # Save table to file
    out_path = ARTIFACTS / "metrics_table.txt"
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(table_txt)
        f.write("\n")

if __name__ == "__main__":
    main()
