from __future__ import annotations
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SRC = ROOT / "src"

OPTIONAL_STEPS = {"01_fetch_us_sources.py"}

steps = [
    "01_fetch_us_sources.py",
    "02_compute_priors.py",
    "03_generate_data.py",
    "04_validate_and_score.py",
    "05_autoencoder_anomalies.py",
    "06_report.py",
]

for step in steps:
    print(f"=== Running {step} ===")
    try:
        subprocess.run([sys.executable, str(SRC / step)], check=True)
    except subprocess.CalledProcessError as e:
        if step in OPTIONAL_STEPS:
            print(f"Skipping optional step {step} due to error: {e}")
            continue
        raise

print("All required steps completed.")
