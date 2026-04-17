from __future__ import annotations
import os
import subprocess, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SRC = ROOT / "src"

SEED = int(os.environ.get("SYNTH_SEED", "42"))
N_HOUSEHOLDS = int(os.environ.get("SYNTH_N_HOUSEHOLDS", "5000"))
PRIORS_SOURCE = os.environ.get("SYNTH_PRIORS_SOURCE", "acs")

steps = [
    ("01_compute_priors.py", ["--source", PRIORS_SOURCE]),
    ("02_generate_data.py", ["--n-households", str(N_HOUSEHOLDS), "--seed", str(SEED)]),
    ("03_validate_and_score.py", []),
    ("04_autoencoder_anomalies.py", []),
    ("05_report.py", []),
]

for step, args in steps:
    print(f"=== Running {step} ===")
    subprocess.run([sys.executable, str(SRC / step), *args], check=True)

print("All steps completed.")
