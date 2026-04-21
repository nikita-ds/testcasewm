from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

import pandas as pd

from money_rounding import is_money_field_path
from normalization import is_state_like_field, state_variants


def _load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _iter_dialog_evidence_files(dialogs_dir: Path) -> Iterable[Path]:
    yield from sorted(dialogs_dir.glob("DIALOG_*_evidence.json"))


def _safe_str(x: Any) -> str:
    return "" if x is None else str(x)


def _stringify_value(v: Any) -> str:
    if v is None:
        return ""
    if isinstance(v, bool):
        return "true" if v else "false"
    return str(v)


def _value_variants(v: Any, *, field_path: str = "") -> List[str]:
    out: List[str] = []
    if is_state_like_field(field_path):
        out.extend(state_variants(v, _stringify_value))
    s = _stringify_value(v).strip()
    if s:
        out.append(s)

    try:
        fv = float(v)
        iv = int(round(fv))
        out.append(str(fv))
        out.append(str(iv))
        out.append(f"{iv:,}")
        out.append(f"${iv}")
        out.append(f"${iv:,}")
        if abs(fv) >= 1000:
            k = fv / 1000.0
            out.append(f"{k:.1f}k")
            out.append(f"${k:.1f}k")
    except Exception:
        pass

    seen: set[str] = set()
    uniq: List[str] = []
    for x in out:
        x2 = str(x).strip()
        if not x2 or x2 in seen:
            continue
        seen.add(x2)
        uniq.append(x2)
    return uniq


def _contains_any(haystack: str, needles: List[str]) -> bool:
    hs = (haystack or "").lower()
    for n in needles:
        if n and str(n).lower() in hs:
            return True
    return False


def _requires_exact_strict_match(field_path: str, value: Any) -> bool:
    if is_money_field_path(field_path):
        return True
    return isinstance(value, (int, float)) and not isinstance(value, bool)


@dataclass(frozen=True)
class EvidenceRow:
    household_id: str
    dialog_id: str
    scenario_name: str
    field_path: str
    record_type: str
    record_id: str
    status: str
    strict_match: bool
    error: int


def _evidence_rows_from_file(
    path: Path,
    *,
    strict: bool,
) -> Tuple[Dict[str, Any], List[EvidenceRow]]:
    ev = _load_json(path)
    meta = ev.get("meta") or {}
    household_id = _safe_str(meta.get("household_id"))
    dialog_id = _safe_str(meta.get("dialog_id"))
    scenario_name = _safe_str(meta.get("scenario_name"))

    rows: List[EvidenceRow] = []
    for item in (ev.get("items") or []):
        field_path = _safe_str(item.get("field_path"))
        record_type = _safe_str(item.get("record_type"))
        record_id = _safe_str(item.get("record_id"))
        status = _safe_str(item.get("status") or "unknown")
        evidence_text = _safe_str(item.get("evidence_text"))
        src_val = item.get("source_value")

        if _requires_exact_strict_match(field_path, src_val):
            variants = _value_variants(src_val, field_path=field_path)
            strict_match = bool(variants) and _contains_any(evidence_text, variants)
        else:
            strict_match = status in {"present", "approximate"}

        # Error logic:
        # - Always error on missing/contradiction.
        # - In strict mode, also error if strict_match is False.
        base_error = 1 if status in {"missing", "contradiction"} else 0
        strict_error = 1 if (strict and not strict_match) else 0
        error = 1 if (base_error or strict_error) else 0

        rows.append(
            EvidenceRow(
                household_id=household_id,
                dialog_id=dialog_id,
                scenario_name=scenario_name,
                field_path=field_path,
                record_type=record_type,
                record_id=record_id,
                status=status,
                strict_match=bool(strict_match),
                error=int(error),
            )
        )

    return ev, rows


def main() -> None:
    p = argparse.ArgumentParser(description="Aggregate evidence validation across dialogs into sparse matrices and summaries")
    p.add_argument("--dialogs-dir", type=Path, default=Path("02_dialogs_generation/artifacts/dialogs"))
    p.add_argument("--out-dir", type=Path, default=Path("02_dialogs_generation/artifacts/validation"))
    p.add_argument("--strict", action="store_true", help="Treat non-matching values as errors (in addition to missing/contradiction)")

    args = p.parse_args()
    dialogs_dir: Path = args.dialogs_dir
    out_dir: Path = args.out_dir
    out_dir.mkdir(parents=True, exist_ok=True)

    files = list(_iter_dialog_evidence_files(dialogs_dir))
    if not files:
        raise SystemExit(f"No evidence files found in {dialogs_dir} (expected DIALOG_*_evidence.json)")

    all_rows: List[EvidenceRow] = []
    for f in files:
        _ev, rows = _evidence_rows_from_file(f, strict=bool(args.strict))
        all_rows.extend(rows)

    df = pd.DataFrame([r.__dict__ for r in all_rows])

    # Sparse error matrix (triples): household_id, field_path, error
    sparse = df.loc[:, ["household_id", "scenario_name", "field_path", "error", "status", "strict_match"]].copy()

    # In case of duplicates (shouldn't happen), take max(error).
    sparse = (
        sparse.groupby(["household_id", "scenario_name", "field_path"], as_index=False)
        .agg({"error": "max", "status": "first", "strict_match": "min"})
        .sort_values(["household_id", "field_path"])
    )

    sparse_path = out_dir / "errors_sparse.parquet"
    sparse.to_parquet(sparse_path, index=False)

    # Field-level summary
    by_field = (
        sparse.groupby("field_path", as_index=False)
        .agg(
            dialogs=("household_id", "nunique"),
            error_rate=("error", "mean"),
            errors=("error", "sum"),
        )
        .sort_values(["error_rate", "errors"], ascending=False)
    )
    by_field.to_csv(out_dir / "summary_by_field.csv", index=False)

    # Scenario-level summary
    by_scenario = (
        sparse.groupby("scenario_name", as_index=False)
        .agg(
            dialogs=("household_id", "nunique"),
            error_rate=("error", "mean"),
            errors=("error", "sum"),
        )
        .sort_values(["error_rate", "errors"], ascending=False)
    )
    by_scenario.to_csv(out_dir / "summary_by_scenario.csv", index=False)

    # Optional: dense pivot (can be huge). We write only if reasonably small.
    n_households = sparse["household_id"].nunique()
    n_fields = sparse["field_path"].nunique()
    if n_households * n_fields <= 250_000:
        dense = sparse.pivot_table(index="household_id", columns="field_path", values="error", fill_value=0, aggfunc="max")
        dense.to_csv(out_dir / "errors_dense.csv")

    meta = {
        "dialogs_dir": str(dialogs_dir),
        "out_dir": str(out_dir),
        "strict": bool(args.strict),
        "num_dialogs": int(n_households),
        "num_fields": int(n_fields),
        "num_cells": int(len(sparse)),
    }
    (out_dir / "run_meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print(f"Wrote: {sparse_path}")
    print(f"Wrote: {out_dir / 'summary_by_field.csv'}")
    print(f"Wrote: {out_dir / 'summary_by_scenario.csv'}")


if __name__ == "__main__":
    main()
