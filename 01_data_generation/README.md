# US RIA-like synthetic household pipeline

This package generates synthetic household-level financial data for affluent, advisor-served US households.

## What is new in this version
- income generation uses **open Census HINC-06 2024 affluent-bracket shares**
- wealth is segmented into **affluent / HNW / ultra**
- payment and ratio plots are cleaned:
  - zeros removed from amount histograms
  - upper tail clipped for readability
  - mortgage ratio plotted on a bounded 0–0.70 axis
- notebook removed; all outputs are generated in the report step

## Pipeline
- `src/01_compute_priors.py` (builds `artifacts/computed_priors.json` from open Census ACS via `api.census.gov`, cached)
- `src/02_generate_data.py`
- `src/03_validate_and_score.py`
- `src/04_autoencoder_anomalies.py`
- `src/05_report.py`

### Priors (open data)
- The only input consumed by generation/validation is `artifacts/computed_priors.json`.
- `src/01_compute_priors.py` fetches public Census ACS aggregates (no API key) and caches raw responses under `artifacts/public_data_cache/` for reproducibility/offline reruns.
- The API access code lives in `src/public_priors.py` (helpers `census_get()` and `census_variables()`).
- If the network is unavailable, run `python src/01_compute_priors.py --source config` to use `config/priors.json` as a fallback.

## Run
### Local
```bash
python run_all.py
```

### Docker
```bash
docker compose up --build
```


Patched in v2: property value generation now handles lower-asset households safely and avoids invalid uniform ranges.

Patched in v3:
- removed `uniform` from key financial amount generation paths
- property values now use beta-shaped bounded sampling
- investable assets / alimony / non-mortgage payments use capped lognormal draws
- fixed the invalid property range bug causing `ValueError: high - low < 0`
