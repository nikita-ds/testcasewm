from __future__ import annotations
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SRC = ROOT / "src"

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
    subprocess.run([sys.executable, str(SRC / step)], check=True)

print("All steps completed.")
