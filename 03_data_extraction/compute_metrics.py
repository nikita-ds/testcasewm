"""
Extraction quality metrics computation module for pipeline results.
"""
import json
from pathlib import Path
from collections import defaultdict
from tabulate import tabulate

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
    with open(path, encoding="utf-8") as f:
        lines = [l.strip().split(",") for l in f if l.strip()]
    header = lines[0]
    return [dict(zip(header, row)) for row in lines[1:]]

def main():
    # 1. Overall dialog-level metrics
    acc = load_json(ACCURACY_REPORT)
    dialog_stats = acc.get("dialog_stats", [])

    n = len(dialog_stats)
    if n == 0:
        print("No dialogs found in accuracy_report.json. Metrics not computed.")
        table_txt = tabulate([], headers=["Entity", "Missed", "Errors", "Invented", "Total cells"], tablefmt="github")
        out_path = ARTIFACTS / "metrics_table.txt"
        with open(out_path, "w", encoding="utf-8") as f:
            f.write(table_txt)
            f.write("\n")
        return

    n_100 = sum(1 for d in dialog_stats if d.get("fraction", 0) >= 1.0)
    n_95 = sum(1 for d in dialog_stats if d.get("fraction", 0) >= 0.95)
    n_90 = sum(1 for d in dialog_stats if d.get("fraction", 0) >= 0.90)
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
        entity_metrics[entity]["missing"] += int(row["missing_extracted"])
        entity_metrics[entity]["error"] += int(row["value_mismatch"])
        entity_metrics[entity]["extra"] += int(row["extra_extracted"])
        entity_metrics[entity]["total"] += int(row["total_cells"])

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
