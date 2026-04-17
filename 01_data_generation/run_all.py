from __future__ import annotations
import subprocess, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SRC = ROOT / "src"

for step in ["01_compute_priors.py","02_generate_data.py","03_validate_and_score.py","04_autoencoder_anomalies.py","05_report.py"]:
    print(f"=== Running {step} ===")
    subprocess.run([sys.executable, str(SRC / step)], check=True)

print("All steps completed.")
