from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from typing import Any, Dict, List, Optional

from normalization import is_state_like_field, state_variants


def _load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _as_str(v: Any) -> str:
    if v is None:
        return ""
    return str(v)


def _value_variants_for_evidence(v: Any, *, field_path: str = "") -> List[str]:
    """Simple, deterministic variants to sanity-check evidence_text.

    This is intentionally conservative: it's for diagnostics only.
    """

    out: List[str] = []
    if is_state_like_field(field_path):
        out.extend(state_variants(v, _as_str))
    s = _as_str(v).strip()
    if s:
        out.append(s)

    try:
        fv = float(v)
        out.append(f"{fv}")
        out.append(f"{fv:.2f}")
        out.append(f"{fv:.2f}%")
        iv = int(round(fv))
        out.append(str(iv))
        out.append(f"{iv:,}")
        out.append(f"${iv}")
        out.append(f"${iv:,}")
    except Exception:
        pass

    # de-dup
    seen: set[str] = set()
    uniq: List[str] = []
    for x in out:
        x2 = str(x).strip()
        if not x2 or x2 in seen:
            continue
        seen.add(x2)
        uniq.append(x2)
    return uniq


def _contains_any(text: str, needles: List[str]) -> bool:
    tlow = (text or "").lower()
    for n in needles:
        if n and str(n).lower() in tlow:
            return True
    return False


def _summarize_dialog(dialog_id: str, dialogs_dir: Path) -> str:
    metrics_path = dialogs_dir / f"{dialog_id}_metrics.json"
    evidence_path = dialogs_dir / f"{dialog_id}_evidence.json"

    if not metrics_path.exists():
        return f"{dialog_id}: missing metrics file ({metrics_path})"
    if not evidence_path.exists():
        return f"{dialog_id}: missing evidence file ({evidence_path})"

    metrics: Dict[str, Any] = _load_json(metrics_path)
    evidence: Dict[str, Any] = _load_json(evidence_path)

    items_by_tid: Dict[str, Dict[str, Any]] = {}
    for it in evidence.get("items") or []:
        tid = str(it.get("target_id") or "")
        if tid:
            items_by_tid[tid] = it

    lines: List[str] = []
    lines.append(f"{dialog_id} | passed={metrics.get('passed')} strict={metrics.get('strict')} format_ok={metrics.get('format_ok')} coverage_lenient={metrics.get('coverage_lenient')} coverage_strict={metrics.get('coverage_strict')}")

    failed = metrics.get("lenient_failed_fields") or []
    if not failed:
        lines.append("  lenient_failed_fields: (none)")
        return "\n".join(lines)

    lines.append(f"  lenient_failed_fields: {len(failed)}")
    for f in failed:
        tid = str(f.get("target_id") or "")
        field_path = str(f.get("field_path") or "")
        status = str(f.get("status") or "")
        src = f.get("source_value")
        lines.append(f"  - {tid} | {status} | {field_path} | source_value={src!r}")

        it = items_by_tid.get(tid)
        if not it:
            lines.append("      evidence: (missing item in evidence.json)")
            continue

        ev_status = str(it.get("status") or "")
        ev_text = str(it.get("evidence_text") or "")
        notes = str(it.get("notes") or "")
        lines.append(f"      evidence_status={ev_status}")
        if notes:
            lines.append(f"      notes={notes}")

        # Basic sanity: contradiction but evidence_text contains source value.
        if ev_status == "contradiction":
            variants = _value_variants_for_evidence(src, field_path=field_path)
            if _contains_any(ev_text, variants):
                lines.append("      !! looks_like_false_contradiction: evidence_text contains source_value variant")

        if ev_text:
            ev_one_line = " ".join([x.strip() for x in ev_text.splitlines() if x.strip()])
            if len(ev_one_line) > 240:
                ev_one_line = ev_one_line[:240] + "…"
            lines.append(f"      evidence_excerpt={ev_one_line}")

    return "\n".join(lines)


def main() -> None:
    p = argparse.ArgumentParser(description="Diagnose dialog validation failures using *_metrics.json and *_evidence.json")
    p.add_argument("--dialogs-dir", type=Path, default=Path("artifacts/dialogs"), help="Directory containing DIALOG_* artifacts")
    p.add_argument("--failures-csv", type=Path, default=Path("artifacts/dialogs/validation_failures.csv"), help="CSV produced by pipeline")
    p.add_argument("--dialog-id", type=str, default=None, help="Diagnose a single dialog id (e.g. DIALOG_HH000205)")
    p.add_argument("--limit", type=int, default=10, help="Max number of failures to print when using failures CSV")
    args = p.parse_args()

    dialogs_dir = args.dialogs_dir

    if args.dialog_id:
        print(_summarize_dialog(str(args.dialog_id), dialogs_dir))
        return

    if not args.failures_csv.exists():
        raise SystemExit(f"Missing failures CSV: {args.failures_csv}")

    with args.failures_csv.open("r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        rows = list(reader)

    if not rows:
        print("No failures in failures CSV.")
        return

    for i, r in enumerate(rows[: max(1, int(args.limit))], start=1):
        dialog_id = str(r.get("dialog_id") or "").strip()
        if not dialog_id:
            continue
        print(f"\n== Failure {i}/{min(len(rows), int(args.limit))} ==")
        print(_summarize_dialog(dialog_id, dialogs_dir))


if __name__ == "__main__":
    main()
