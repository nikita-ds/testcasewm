# US RIA-like synthetic household pipeline

This package generates synthetic household-level financial data for affluent, advisor-served US households.

## What is new in this version
- income generation uses a **smooth lognormal model** anchored to an open Census median (ACS when available)
- income is **calibrated** so mean household income is approximately a configurable multiple of the public median (default: 2×)
- wealth is segmented into **affluent / HNW / ultra**
- investable assets are weakly tied to income with configurable caps to avoid implausible low-income / ultra-high-asset combos
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

### Generator knobs (no “magic constants”)
- Curated parameters that are not derivable from open data live under `generator_params`.
- In offline mode (`--source config`) these parameters come from `config/priors.json`.
- In ACS mode they are deep-merged into `artifacts/computed_priors.json` by the priors builder.

## Run
### Local
```bash
python run_all.py
```

Environment variables (optional):
- `SYNTH_SEED` (default: `42`) — ensures deterministic generation
- `SYNTH_N_HOUSEHOLDS` (default: `5000`)
- `SYNTH_PRIORS_SOURCE` (default: `acs`, choices: `acs|config`)

Example:
```bash
SYNTH_SEED=42 SYNTH_N_HOUSEHOLDS=200 SYNTH_PRIORS_SOURCE=config python run_all.py
```

### Docker
```bash
docker compose up --build
```

Docker also respects the same env vars:
```bash
SYNTH_SEED=42 SYNTH_N_HOUSEHOLDS=200 SYNTH_PRIORS_SOURCE=config docker compose up --build
```


Patched in v2: property value generation now handles lower-asset households safely and avoids invalid uniform ranges.

Patched in v3:
- removed `uniform` from key financial amount generation paths
- property values now use beta-shaped bounded sampling
- investable assets / alimony / non-mortgage payments use capped lognormal draws
- fixed the invalid property range bug causing `ValueError: high - low < 0`

## Outputs
- Tables: `artifacts/tables/*.csv`
- Figures: `artifacts/figures/*.png`
- Report markdown: `artifacts/report/report.md`

Notable figures:
- `income_vs_investable_assets.png` — cross-plot to spot income/asset consistency issues
