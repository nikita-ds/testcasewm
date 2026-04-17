from __future__ import annotations
import json
from pathlib import Path
try:
    import requests
except Exception:
    requests = None
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "data" / "raw"
RAW.mkdir(parents=True, exist_ok=True)
ART = ROOT / "artifacts"
ART.mkdir(parents=True, exist_ok=True)

SOURCES = {
    "census_income_2023.html": "https://www.census.gov/library/publications/2024/demo/p60-282.html",
    "sipp_wealth_2023.html": "https://www.census.gov/library/publications/2025/demo/p70br-211.html",
    "bls_cex_2024.html": "https://www.bls.gov/news.release/cesan.nr0.htm",
    "fed_scf_index.html": "https://www.federalreserve.gov/econres/scfindex.htm",
}

def fetch(url: str, out: Path) -> None:
    if out.exists() and out.stat().st_size > 0:
        return
    if requests is not None:
        r = requests.get(url, timeout=60, headers={"User-Agent":"Mozilla/5.0"})
        r.raise_for_status()
        out.write_bytes(r.content)
        return
    req = Request(url, headers={"User-Agent":"Mozilla/5.0"})
    with urlopen(req, timeout=60) as resp:
        out.write_bytes(resp.read())

def main():
    manifest = []
    for fname, url in SOURCES.items():
        out = RAW / fname
        fetch(url, out)
        manifest.append({"file": str(out), "url": url})
    (ART / "source_manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print("Fetched official source pages into", RAW)

if __name__ == "__main__":
    main()
