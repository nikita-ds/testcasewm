from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402


@dataclass(frozen=True)
class Paths:
    realism_passed_dir: Path
    financial_profiles_json: Path
    output_dir: Path
    pairs_path: Path
    figures_dir: Path
    summary_path: Path


def _repo_root() -> Path:
    # run.py lives in <repo>/03_data_extraction/run.py
    return Path(__file__).resolve().parents[1]


def _load_profiles(path: Path) -> Dict[str, Dict[str, Any]]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, list):
        raise ValueError(f"Expected a list in {path}")

    out: Dict[str, Dict[str, Any]] = {}
    for item in data:
        if not isinstance(item, dict):
            continue
        hh = item.get("household_id")
        if hh is None:
            hh = (item.get("households") or {}).get("household_id")
        hh = str(hh or "").strip()
        if not hh:
            continue
        out[hh] = item
    return out


def _iter_dialog_ids(realism_dir: Path) -> List[str]:
    ids: set[str] = set()
    for p in realism_dir.glob("DIALOG_*.*"):
        if not p.is_file():
            continue
        name = p.name
        if not name.startswith("DIALOG_"):
            continue
        if name.endswith("_metrics.json") or name.endswith("_evidence.json"):
            continue
        if name.endswith("_deepseek_judge.json"):
            # judge file is auxiliary; dialog_id is still the prefix
            ids.add(name[: -len("_deepseek_judge.json")])
            continue
        if name.endswith(".json"):
            ids.add(name[: -len(".json")])
            continue
        if name.endswith(".txt"):
            ids.add(name[: -len(".txt")])
            continue
    return sorted(ids)


def _load_dialog_text(realism_dir: Path, dialog_id: str) -> str:
    txt_path = realism_dir / f"{dialog_id}.txt"
    if txt_path.exists():
        return txt_path.read_text(encoding="utf-8")

    json_path = realism_dir / f"{dialog_id}.json"
    if json_path.exists():
        obj = json.loads(json_path.read_text(encoding="utf-8"))
        if isinstance(obj, dict):
            for k in ("transcript", "transcript_skeleton"):
                v = obj.get(k)
                if isinstance(v, str) and v.strip():
                    return v
    return ""


def _profile_scenario(profile: Dict[str, Any]) -> str:
    hh = profile.get("households") or {}
    scen = hh.get("scenario")
    return str(scen or "").strip() or "unknown"


def _profile_income(profile: Dict[str, Any]) -> Optional[float]:
    hh = profile.get("households") or {}
    v = hh.get("annual_household_gross_income")
    try:
        return None if v is None else float(v)
    except Exception:
        return None


def _profile_assets_total(profile: Dict[str, Any]) -> Optional[float]:
    hh = profile.get("households") or {}
    investable = hh.get("investable_assets_total")
    property_value = hh.get("property_value_total")
    try:
        investable_f = None if investable is None else float(investable)
    except Exception:
        investable_f = None
    try:
        property_f = None if property_value is None else float(property_value)
    except Exception:
        property_f = None

    if investable_f is None and property_f is None:
        return None
    return float((investable_f or 0.0) + (property_f or 0.0))


def _ensure_dirs(paths: Paths) -> None:
    paths.output_dir.mkdir(parents=True, exist_ok=True)
    paths.figures_dir.mkdir(parents=True, exist_ok=True)


def _plot_hist(values: List[float], *, title: str, xlabel: str, out_path: Path) -> None:
    plt.figure(figsize=(10, 6))
    plt.hist(values, bins=40)
    plt.title(title)
    plt.xlabel(xlabel)
    plt.ylabel("Households")
    plt.tight_layout()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    plt.savefig(out_path)
    plt.close()


def _plot_scenarios(scenarios: List[str], *, out_path: Path) -> None:
    counts: Dict[str, int] = {}
    for s in scenarios:
        counts[s] = counts.get(s, 0) + 1

    items = sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))
    labels = [k for k, _ in items]
    vals = [v for _, v in items]

    plt.figure(figsize=(12, 6))
    plt.bar(range(len(labels)), vals)
    plt.xticks(range(len(labels)), labels, rotation=45, ha="right")
    plt.title("Scenario distribution (realism_passed)")
    plt.ylabel("Households")
    plt.tight_layout()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    plt.savefig(out_path)
    plt.close()


def main() -> None:
    repo_root = _repo_root()

    realism_dir = Path(
        os.environ.get(
            "REALISM_PASSED_DIR",
            str(repo_root / "02_dialogs_generation" / "artifacts" / "dialogs" / "realism_passed"),
        )
    ).resolve()
    profiles_path = Path(
        os.environ.get(
            "FINANCIAL_PROFILES_JSON",
            str(repo_root / "02_dialogs_generation" / "artifacts" / "financial_profiles.json"),
        )
    ).resolve()

    output_dir = Path(os.environ.get("OUTPUT_DIR", "./artifacts")).resolve()
    pairs_basename = str(os.environ.get("PAIRS_BASENAME", "ground_truth_pairs.jsonl")).strip() or "ground_truth_pairs.jsonl"

    paths = Paths(
        realism_passed_dir=realism_dir,
        financial_profiles_json=profiles_path,
        output_dir=output_dir,
        pairs_path=output_dir / pairs_basename,
        figures_dir=output_dir / "figures",
        summary_path=output_dir / "summary.json",
    )

    _ensure_dirs(paths)

    if not paths.realism_passed_dir.exists():
        raise SystemExit(f"Missing realism_passed dir: {paths.realism_passed_dir}")
    if not paths.financial_profiles_json.exists():
        raise SystemExit(f"Missing financial profiles json: {paths.financial_profiles_json}")

    profiles = _load_profiles(paths.financial_profiles_json)
    dialog_ids = _iter_dialog_ids(paths.realism_passed_dir)

    n_total = 0
    n_written = 0
    n_missing_profile = 0
    n_missing_dialog_text = 0

    incomes: List[float] = []
    assets: List[float] = []
    scenarios: List[str] = []

    with paths.pairs_path.open("w", encoding="utf-8") as f:
        for dialog_id in dialog_ids:
            n_total += 1
            hh_id = dialog_id[len("DIALOG_") :] if dialog_id.startswith("DIALOG_") else dialog_id
            profile = profiles.get(hh_id)
            if profile is None:
                n_missing_profile += 1
                continue

            dialog_text = _load_dialog_text(paths.realism_passed_dir, dialog_id)
            if not dialog_text.strip():
                n_missing_dialog_text += 1

            scen = _profile_scenario(profile)

            inc = _profile_income(profile)
            if inc is not None:
                incomes.append(inc)

            ast = _profile_assets_total(profile)
            if ast is not None:
                assets.append(ast)

            scenarios.append(scen)

            row = {
                "household_id": hh_id,
                "dialog_id": dialog_id,
                "scenario": scen,
                "profile": profile,
                "dialog": dialog_text,
            }
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
            n_written += 1

    if assets:
        _plot_hist(
            assets,
            title="Assets (investable + property)",
            xlabel="USD",
            out_path=paths.figures_dir / "assets_hist.png",
        )

    if incomes:
        _plot_hist(
            incomes,
            title="Annual household gross income",
            xlabel="USD/year",
            out_path=paths.figures_dir / "income_hist.png",
        )

    if scenarios:
        _plot_scenarios(scenarios, out_path=paths.figures_dir / "scenario_distribution.png")

    summary = {
        "realism_passed_dir": str(paths.realism_passed_dir),
        "financial_profiles_json": str(paths.financial_profiles_json),
        "pairs_path": str(paths.pairs_path),
        "num_dialog_ids_seen": n_total,
        "num_pairs_written": n_written,
        "num_missing_profile": n_missing_profile,
        "num_missing_dialog_text": n_missing_dialog_text,
        "num_incomes": len(incomes),
        "num_assets": len(assets),
        "num_scenarios": len(scenarios),
    }
    paths.summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print(json.dumps(summary, ensure_ascii=False))


if __name__ == "__main__":
    main()
