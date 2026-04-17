from __future__ import annotations

import argparse
import json
from pathlib import Path

from public_priors import build_priors_with_fallback


ROOT = Path(__file__).resolve().parent.parent
CFG = ROOT / "config"
ART = ROOT / "artifacts"
ART.mkdir(parents=True, exist_ok=True)


def main() -> None:
    ap = argparse.ArgumentParser(
        description=(
            "Compute and persist generation priors into artifacts/computed_priors.json. "
            "By default pulls open data from Census ACS via the public api.census.gov endpoint "
            "(responses are cached under artifacts/public_data_cache/)."
        )
    )
    ap.add_argument(
        "--source",
        choices=["acs", "config"],
        default="acs",
        help=(
            "Where to build priors from. 'acs' uses open Census ACS via api.census.gov (cached). "
            "'config' uses config/priors.json (offline/CI friendly)."
        ),
    )
    args = ap.parse_args()

    priors = build_priors_with_fallback(
        cfg_priors_path=CFG / "priors.json",
        artifacts_path=ART,
        prefer_acs=(args.source == "acs"),
    )

    (ART / "computed_priors.json").write_text(json.dumps(priors, indent=2), encoding="utf-8")
    print("Wrote", ART / "computed_priors.json")


if __name__ == "__main__":
    main()
