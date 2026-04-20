from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

from env_utils import load_dotenv_if_present


def _run(cmd: list[str]) -> None:
    proc = subprocess.run(cmd, text=True)
    if proc.returncode != 0:
        raise SystemExit(proc.returncode)


def _truthy_env(name: str, default: bool = False) -> bool:
    v = str(os.environ.get(name, "") or "").strip().lower()
    if not v:
        return default
    return v in {"1", "true", "yes", "y", "on"}


def _resolve_grounded_paths(base: Path) -> tuple[Path, Path]:
    """Return (evidence_dir, grounded_out_json)."""

    repo_root = base.parent
    default_evidence_dir = repo_root / "02_dialogs_generation" / "artifacts" / "dialogs"
    evidence_dir = Path(os.environ.get("EVIDENCE_DIALOGS_DIR", str(default_evidence_dir)) or str(default_evidence_dir)).resolve()

    default_grounded_out = repo_root / "02_dialogs_generation" / "artifacts" / "grounded_financial_profiles.json"
    grounded_out = Path(os.environ.get("GROUNDED_PROFILES_JSON", str(default_grounded_out)) or str(default_grounded_out)).resolve()

    return evidence_dir, grounded_out


def _maybe_export_grounded_profiles(base: Path) -> None:
    """Generate grounded profiles JSON from evidence if configured and evidence exists."""

    if not _truthy_env("AUTO_EXPORT_GROUNDED_PROFILES", default=True):
        return

    evidence_dir, grounded_out = _resolve_grounded_paths(base)

    if not evidence_dir.exists():
        print(
            json.dumps(
                {
                    "step": "export_grounded_profiles",
                    "status": "skipped",
                    "reason": "missing_evidence_dir",
                    "evidence_dir": str(evidence_dir),
                },
                ensure_ascii=False,
            )
        )
        return

    # Evidence JSON may live either directly under dialogs_dir or inside realism_passed.
    evidence_files = sorted(evidence_dir.glob("DIALOG_*_evidence.json"))
    if not evidence_files:
        rp = evidence_dir / "realism_passed"
        if rp.exists():
            rp_files = sorted(rp.glob("DIALOG_*_evidence.json"))
            if rp_files:
                evidence_dir = rp
                evidence_files = rp_files

    if not evidence_files:
        print(
            json.dumps(
                {
                    "step": "export_grounded_profiles",
                    "status": "skipped",
                    "reason": "no_evidence_files",
                    "evidence_dir": str(evidence_dir),
                },
                ensure_ascii=False,
            )
        )
        return

    if grounded_out.exists() and not _truthy_env("FORCE_REBUILD_GROUNDED_PROFILES", default=False):
        print(
            json.dumps(
                {
                    "step": "export_grounded_profiles",
                    "status": "skipped",
                    "reason": "already_exists",
                    "out_json": str(grounded_out),
                    "evidence_dir": str(evidence_dir),
                    "evidence_files": len(evidence_files),
                },
                ensure_ascii=False,
            )
        )
        return

    cmd = [
        sys.executable,
        str(base / "export_grounded_profiles.py"),
        "--dialogs-dir",
        str(evidence_dir),
        "--out-json",
        str(grounded_out),
    ]
    if _truthy_env("INCLUDE_APPROXIMATE_GROUNDED", default=False):
        cmd.append("--include-approximate")
    print(json.dumps({"step": "export_grounded_profiles", "cmd": cmd}, ensure_ascii=False))
    _run(cmd)


def main() -> int:
    # Order required by spec: reports/graphs first, then extraction, then merge.
    base = Path(__file__).resolve().parent

    # Load .env so EXTRACTION_LIMIT/WORKERS are visible even outside Docker.
    load_dotenv_if_present(base)

    extraction_limit = 0
    try:
        extraction_limit = int(str(os.environ.get("EXTRACTION_LIMIT", "0") or "0").strip())
    except Exception:
        extraction_limit = 0

    force_reextract = _truthy_env("EXTRACTION_FORCE_REEXTRACT", default=False)

    output_dir = Path(os.environ.get("OUTPUT_DIR", str(base / "artifacts")) or str(base / "artifacts")).resolve()
    pairs_path = output_dir / "ground_truth_pairs.jsonl"
    extracted_dir = output_dir / "extracted"
    merged_jsonl = output_dir / "merged" / "merged_ground_truth_extracted.jsonl"
    joint_dataset = output_dir / "joint_dataset.jsonl"
    hist_path = output_dir / "figures" / "extraction_accuracy_hist.png"
    dialogs_dir = Path(
        os.environ.get(
            "REALISM_PASSED_DIR",
            str(base.parent / "02_dialogs_generation" / "artifacts" / "dialogs" / "realism_passed"),
        )
        or str(base.parent / "02_dialogs_generation" / "artifacts" / "dialogs" / "realism_passed")
    ).resolve()

    extracted_dir.mkdir(parents=True, exist_ok=True)

    # Optional: build dialog-grounded GT from evidence before pairing.
    _maybe_export_grounded_profiles(base)

    # Ensure run.py only produces ground-truth pairs + plots.
    # Otherwise it may auto-run build/eval/discrepancy if extracted artifacts exist,
    # and we'll end up running the later steps twice.
    run_reports_cmd = [sys.executable, str(base / "run.py"), "--reports-only"]
    print(json.dumps({"step": "reports_and_plots", "cmd": run_reports_cmd}, ensure_ascii=False))
    _run(run_reports_cmd)

    if force_reextract:
        cmd = [
            sys.executable,
            str(base / "extract_from_dialogs.py"),
            "--dialogs-dir",
            str(dialogs_dir),
            "--out-dir",
            str(extracted_dir),
        ]
        if extraction_limit and extraction_limit > 0:
            cmd += ["--limit", str(extraction_limit)]
        print(
            json.dumps(
                {
                    "step": "extract_from_dialogs",
                    "cmd": cmd,
                    "mode": "force_reextract",
                },
                ensure_ascii=False,
            )
        )
        _run(cmd)
    else:
        # If we already have enough extracted dialogs for the requested limit,
        # skip extraction and go straight to metrics.
        if extraction_limit and extraction_limit > 0:
            existing = sorted(extracted_dir.glob("DIALOG_*.extracted.json"))
            if len(existing) >= extraction_limit:
                print(
                    json.dumps(
                        {
                            "step": "extract_from_dialogs",
                            "status": "skipped",
                            "reason": "already_extracted",
                            "existing_extracted": len(existing),
                            "extraction_limit": extraction_limit,
                        },
                        ensure_ascii=False,
                    )
                )
            else:
                cmd = [
                    sys.executable,
                    str(base / "extract_from_dialogs.py"),
                    "--skip-existing",
                    "--dialogs-dir",
                    str(dialogs_dir),
                    "--out-dir",
                    str(extracted_dir),
                ]
                # Keep the limit explicit for clarity.
                cmd += ["--limit", str(extraction_limit)]
                print(json.dumps({"step": "extract_from_dialogs", "cmd": cmd}, ensure_ascii=False))
                _run(cmd)
        else:
            cmd = [
                sys.executable,
                str(base / "extract_from_dialogs.py"),
                "--skip-existing",
                "--dialogs-dir",
                str(dialogs_dir),
                "--out-dir",
                str(extracted_dir),
            ]
            print(json.dumps({"step": "extract_from_dialogs", "cmd": cmd}, ensure_ascii=False))
            _run(cmd)

    build_cmd = [
        sys.executable,
        str(base / "build_joint_dataset.py"),
        "--pairs",
        str(pairs_path),
        "--extracted-dir",
        str(extracted_dir),
        "--out",
        str(joint_dataset),
    ]
    if extraction_limit and extraction_limit > 0:
        build_cmd += ["--limit", str(extraction_limit)]
    print(json.dumps({"step": "build_joint_dataset", "cmd": build_cmd}, ensure_ascii=False))
    _run(build_cmd)

    eval_cmd = [
        sys.executable,
        str(base / "evaluate_extraction.py"),
        "--pairs",
        str(pairs_path),
        "--extracted-dir",
        str(extracted_dir),
        "--out-jsonl",
        str(merged_jsonl),
        "--hist-path",
        str(hist_path),
    ]
    if extraction_limit and extraction_limit > 0:
        eval_cmd += ["--limit", str(extraction_limit)]
    print(json.dumps({"step": "evaluate_extraction", "cmd": eval_cmd}, ensure_ascii=False))
    _run(eval_cmd)

    disc_cmd = [
        sys.executable,
        str(base / "analyze_discrepancies.py"),
        "--merged-jsonl",
        str(merged_jsonl),
        "--out-dir",
        str(output_dir),
    ]
    # Print a small sample of value mismatches by default to make debugging easier.
    # Can be disabled via PRINT_VALUE_MISMATCHES=0.
    if _truthy_env("PRINT_VALUE_MISMATCHES", default=True):
        disc_cmd.append("--print-value-mismatches")
        try:
            limit = int(str(os.environ.get("PRINT_VALUE_MISMATCHES_LIMIT", "30") or "30").strip())
        except Exception:
            limit = 30
        disc_cmd += ["--print-limit", str(max(0, limit))]
    print(json.dumps({"step": "analyze_discrepancies", "cmd": disc_cmd}, ensure_ascii=False))
    _run(disc_cmd)

    # Compute and print/save extraction metrics
    metrics_cmd = [sys.executable, str(base / "compute_metrics.py")]
    print(json.dumps({"step": "compute_metrics", "cmd": metrics_cmd}, ensure_ascii=False))
    _run(metrics_cmd)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
