# US RIA-like synthetic household pipeline (complete)

This project generates synthetic household-level financial data for affluent, advisor-served US households.

## Included
- nested relational schema
- official US anchors
- affluent/RIA priors
- conditional generation with lifecycle-derived dates
- scenario coverage
- PSI- and JS-based validation
- business-rule checks
- real PyTorch autoencoder anomaly detection
- top 5 anomalous households for manual review
- notebook walkthrough
- report generation

## Files
- APPROACH.md
- run_all.py
- config/schema.json
- config/priors_assumptions.json
- src/01_fetch_us_sources.py
- src/02_compute_priors.py
- src/03_generate_data.py
- src/04_validate_and_score.py
- src/05_autoencoder_anomalies.py
- src/06_report.py
- notebooks/01_analysis.ipynb

## Run
python run_all.py

## Docker run

Build and run everything in Docker:

```bash
docker compose up --build
```

This will:
1. install all Python dependencies inside the container
2. run the full pipeline via `run_all.py`
3. write outputs to the mounted `artifacts/` and `data/` folders on your host

To run a single step inside Docker:

```bash
docker compose run --rm synth python src/03_generate_data.py --n-households 5000
```

To open a shell inside the container:

```bash
docker compose run --rm synth bash
```
