from __future__ import annotations

import csv
import datetime as _dt
import json
import logging
from dataclasses import asdict
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple


logger = logging.getLogger(__name__)


def _profile_household_id(profile: Dict[str, Any]) -> str:
    return str(profile.get("household_id") or (profile.get("households") or {}).get("household_id") or "").strip()


def _profile_income(profile: Dict[str, Any]) -> Optional[float]:
    hh = profile.get("households") or {}
    v = hh.get("annual_household_gross_income")
    try:
        return float(v)
    except Exception:
        return None


def _load_registry_status_map(path: Path) -> Dict[str, str]:
    if not path.exists() or path.stat().st_size == 0:
        return {}
    out: Dict[str, str] = {}
    try:
        with path.open("r", encoding="utf-8", newline="") as f:
            r = csv.DictReader(f)
            for row in r:
                hh = str(row.get("household_id") or "").strip()
                if not hh:
                    continue
                st = str(row.get("status") or "unknown").strip().lower() or "unknown"
                out[hh] = st
    except Exception:
        return {}
    return out


def _iter_dialog_json_paths(output_dir: Path, *, deepseek_pass_subdir: str) -> Iterable[Path]:
    if not output_dir.exists():
        return []
    excluded_dirs = {"reports", str(deepseek_pass_subdir or "realism_passed").strip()}
    for p in output_dir.glob("DIALOG_*.json"):
        name = p.name
        if name.endswith("_metrics.json") or name.endswith("_evidence.json") or name.endswith("_deepseek_judge.json"):
            continue
        if p.parent.name in excluded_dirs:
            continue
        yield p


def _load_json_safely(path: Path) -> Optional[Dict[str, Any]]:
    try:
        with path.open("r", encoding="utf-8") as f:
            obj = json.load(f)
        return obj if isinstance(obj, dict) else None
    except Exception:
        return None


def _dialog_income(dialog_obj: Dict[str, Any]) -> Optional[float]:
    prof = dialog_obj.get("financial_profile")
    if not isinstance(prof, dict):
        return None
    return _profile_income(prof)


def _scenario_name(dialog_obj: Dict[str, Any]) -> str:
    return str(dialog_obj.get("scenario") or (dialog_obj.get("metadata") or {}).get("scenario_name") or "").strip() or "(unknown)"


def _household_id_from_dialog_id(dialog_id: str) -> str:
    s = str(dialog_id or "").strip()
    if s.startswith("DIALOG_"):
        return s[len("DIALOG_") :].strip()
    return s


def write_generation_report(
    *,
    cfg: Any,
    attempted_profiles: List[Dict[str, Any]],
    errored_dialog_ids: List[str],
    skipped_dialog_ids: List[str],
) -> Optional[Path]:
    """Aggregate end-of-run metrics and write markdown + json + plots.

    Report focuses on dialogs that PASSED ALL FILTERS:
    - validation (if present)
    - DeepSeek realism judge (if enabled)

    Output:
    - <output_dir>/reports/latest/summary.md
    - <output_dir>/reports/latest/summary.json
    - <output_dir>/reports/latest/scenario_distribution.png
    - <output_dir>/reports/latest/income_histogram.png
    - <output_dir>/reports/latest/records.jsonl
    """

    output_dir = Path(getattr(cfg, "output_dir"))
    output_dir.mkdir(parents=True, exist_ok=True)
    reports_root = output_dir / "reports"
    reports_root.mkdir(parents=True, exist_ok=True)

    timestamp = _dt.datetime.now().strftime("%Y%m%d_%H%M%S")
    report_dir = reports_root / f"report_{timestamp}"
    latest_dir = reports_root / "latest"
    report_dir.mkdir(parents=True, exist_ok=True)
    latest_dir.mkdir(parents=True, exist_ok=True)

    deepseek_enabled = bool(getattr(cfg, "deepseek_realism_check", True))
    deepseek_pass_subdir = str(getattr(cfg, "deepseek_pass_subdir", "realism_passed") or "realism_passed")

    # Attempted base population.
    attempted_hh_ids: List[str] = []
    profile_income_by_hh: Dict[str, Optional[float]] = {}
    for p in attempted_profiles or []:
        hh = _profile_household_id(p)
        if not hh:
            continue
        attempted_hh_ids.append(hh)
        if hh not in profile_income_by_hh:
            profile_income_by_hh[hh] = _profile_income(p)

    attempted_total = len(attempted_hh_ids)

    registry_path = getattr(cfg, "registry_path", None)
    status_by_hh: Dict[str, str] = {}
    if registry_path is not None:
        status_by_hh = _load_registry_status_map(Path(registry_path))

    # Load produced dialog artifacts.
    dialog_by_hh: Dict[str, Dict[str, Any]] = {}
    for path in _iter_dialog_json_paths(output_dir, deepseek_pass_subdir=deepseek_pass_subdir):
        obj = _load_json_safely(path)
        if not obj:
            continue
        dialog_id = str(obj.get("id") or path.stem)
        hh = _household_id_from_dialog_id(dialog_id) or _household_id_from_dialog_id(path.stem)
        if not hh:
            continue
        dialog_by_hh[hh] = obj

    # Per-dialog derived fields.
    records: List[Dict[str, Any]] = []
    validation_checked = 0
    validation_passed = 0
    deepseek_checked = 0
    deepseek_passed = 0
    passed_all = 0

    errored_hh = {_household_id_from_dialog_id(d) for d in (errored_dialog_ids or [])}
    skipped_hh = {_household_id_from_dialog_id(d) for d in (skipped_dialog_ids or [])}

    for hh in attempted_hh_ids:
        dialog_obj = dialog_by_hh.get(hh)
        dialog_id = str((dialog_obj or {}).get("id") or f"DIALOG_{hh}")
        scenario = _scenario_name(dialog_obj) if dialog_obj else "(missing_artifact)"

        metrics = (dialog_obj or {}).get("metrics")
        metrics_pass = None
        if isinstance(metrics, dict):
            if "passed" in metrics:
                validation_checked += 1
                metrics_pass = bool(metrics.get("passed"))
                if metrics_pass:
                    validation_passed += 1

        deepseek = (dialog_obj or {}).get("deepseek_realism")
        deepseek_pass = None
        if isinstance(deepseek, dict):
            deepseek_checked += 1
            deepseek_pass = bool(deepseek.get("passed_threshold"))
            if deepseek_pass:
                deepseek_passed += 1

        # If validation isn't present in this mode, treat it as not-applicable (pass).
        validation_ok = True if metrics_pass is None else bool(metrics_pass)
        if deepseek_enabled:
            # If DeepSeek judge is enabled, we require an explicit pass.
            deepseek_ok = bool(deepseek_pass)
        else:
            deepseek_ok = True

        all_ok = bool(validation_ok and deepseek_ok and (hh not in errored_hh))
        if all_ok:
            passed_all += 1

        income = _dialog_income(dialog_obj) if dialog_obj else profile_income_by_hh.get(hh)
        status = status_by_hh.get(hh)
        if not status:
            if hh in errored_hh:
                status = "error"
            elif hh in skipped_hh:
                status = "validation_failed"
            elif dialog_obj is not None:
                status = "success"
            else:
                status = "unknown"

        records.append(
            {
                "household_id": hh,
                "dialog_id": dialog_id,
                "status": status,
                "scenario": scenario,
                "income": income,
                "validation_checked": metrics_pass is not None,
                "validation_passed": metrics_pass,
                "deepseek_checked": deepseek_pass is not None,
                "deepseek_passed": deepseek_pass,
                "passed_all_filters": all_ok,
            }
        )

    # Scenario distribution + income list for PASSED ALL FILTERS.
    scenario_counts: Dict[str, int] = {}
    passed_incomes: List[float] = []
    for r in records:
        if not r.get("passed_all_filters"):
            continue
        sc = str(r.get("scenario") or "(unknown)")
        scenario_counts[sc] = scenario_counts.get(sc, 0) + 1
        inc = r.get("income")
        if isinstance(inc, (int, float)):
            passed_incomes.append(float(inc))

    scenario_counts_sorted = sorted(scenario_counts.items(), key=lambda kv: (-kv[1], kv[0]))

    summary = {
        "generated_at": _dt.datetime.now().isoformat(timespec="seconds"),
        "output_dir": str(output_dir),
        "attempted_total": attempted_total,
        "errored_total": len(errored_dialog_ids or []),
        "skipped_total": len(skipped_dialog_ids or []),
        "artifacts_total": len(dialog_by_hh),
        "validation_checked_total": validation_checked,
        "validation_passed_total": validation_passed,
        "deepseek_enabled": deepseek_enabled,
        "deepseek_checked_total": deepseek_checked,
        "deepseek_passed_total": deepseek_passed,
        "passed_all_filters_total": passed_all,
        "scenario_distribution_passed_all": [{"scenario": k, "count": v} for k, v in scenario_counts_sorted],
    }

    # Write JSON + JSONL.
    summary_json = report_dir / "summary.json"
    records_jsonl = report_dir / "records.jsonl"
    with summary_json.open("w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)
    with records_jsonl.open("w", encoding="utf-8") as f:
        for r in records:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

    # Plots (matplotlib is optional at runtime; if missing, we still write md/json).
    scenario_png = report_dir / "scenario_distribution.png"
    income_png = report_dir / "income_histogram.png"
    plots_ok = False
    try:
        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt

        # Scenario distribution bar chart.
        plt.figure(figsize=(max(6.0, 0.6 * max(1, len(scenario_counts_sorted))), 4.0))
        labels = [k for k, _ in scenario_counts_sorted] or ["(none)"]
        values = [v for _, v in scenario_counts_sorted] or [0]
        plt.bar(range(len(values)), values)
        plt.xticks(range(len(labels)), labels, rotation=35, ha="right")
        plt.ylabel("Dialogs (passed all filters)")
        plt.title("Scenario distribution")
        plt.tight_layout()
        plt.savefig(scenario_png, dpi=160)
        plt.close()

        # Income histogram.
        plt.figure(figsize=(6.5, 4.0))
        if passed_incomes:
            plt.hist(passed_incomes, bins=min(30, max(5, int(len(passed_incomes) ** 0.5) * 4)))
        else:
            plt.hist([0], bins=1)
        plt.xlabel("Annual household gross income")
        plt.ylabel("Dialogs (passed all filters)")
        plt.title("Income histogram (passed all filters)")
        plt.tight_layout()
        plt.savefig(income_png, dpi=160)
        plt.close()

        plots_ok = True
    except Exception as exc:
        logger.warning("Report plots skipped: %s", exc)

    # Markdown summary.
    md = report_dir / "summary.md"
    lines: List[str] = []
    lines.append("# Dialog generation report")
    lines.append("")
    lines.append(f"Generated at: {summary['generated_at']}")
    lines.append(f"Output dir: {summary['output_dir']}")
    lines.append("")
    lines.append("## Counts")
    lines.append("")
    lines.append(f"- Attempted: {attempted_total}")
    lines.append(f"- Errored: {len(errored_dialog_ids or [])}")
    lines.append(f"- Skipped (validation_failed): {len(skipped_dialog_ids or [])}")
    lines.append(f"- Dialog artifacts written: {len(dialog_by_hh)}")
    lines.append("")
    lines.append("## Filters")
    lines.append("")
    lines.append(f"- Validation checked: {validation_checked}")
    lines.append(f"- Validation passed: {validation_passed}")
    lines.append(f"- DeepSeek enabled: {deepseek_enabled}")
    lines.append(f"- DeepSeek checked: {deepseek_checked}")
    lines.append(f"- DeepSeek passed: {deepseek_passed}")
    lines.append("")
    lines.append(f"## Remaining (passed all filters): {passed_all}")
    lines.append("")
    lines.append("## Scenario distribution (passed all filters)")
    lines.append("")
    if scenario_counts_sorted:
        for sc, cnt in scenario_counts_sorted:
            lines.append(f"- {sc}: {cnt}")
    else:
        lines.append("- (none)")
    lines.append("")
    if plots_ok:
        lines.append("## Plots")
        lines.append("")
        lines.append("- scenario_distribution.png")
        lines.append("- income_histogram.png")
        lines.append("")

    md.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")

    # Update latest (overwrite files).
    for src in [summary_json, records_jsonl, md, scenario_png, income_png]:
        if not src.exists():
            continue
        dst = latest_dir / src.name
        try:
            dst.write_bytes(src.read_bytes())
        except Exception:
            pass

    logger.info("Wrote generation report: %s", md)
    return md
