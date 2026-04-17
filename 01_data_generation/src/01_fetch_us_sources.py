from __future__ import annotations
import json
from pathlib import Path

try:
    import requests
except Exception:
    requests = None

from urllib.request import Request, urlopen
from urllib.error import URLError, HTTPError

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

HEADERS = {
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Cache-Control": "no-cache",
}

def fetch_one(url: str, out: Path) -> dict:
    if out.exists() and out.stat().st_size > 0:
        return {"status": "cached", "bytes": out.stat().st_size, "error": None}

    # Try requests first
    if requests is not None:
        try:
            r = requests.get(url, timeout=60, headers=HEADERS)
            r.raise_for_status()
            out.write_bytes(r.content)
            return {"status": "downloaded", "bytes": len(r.content), "error": None}
        except Exception as e:
            req_error = f"{type(e).__name__}: {e}"
        else:
            req_error = None
    else:
        req_error = "requests_unavailable"

    # Fallback to urllib
    try:
        req = Request(url, headers=HEADERS)
        with urlopen(req, timeout=60) as resp:
            data = resp.read()
        out.write_bytes(data)
        return {"status": "downloaded_fallback", "bytes": len(data), "error": None if req_error is None else req_error}
    except Exception as e:
        return {"status": "failed", "bytes": 0, "error": f"{req_error} | fallback={type(e).__name__}: {e}"}

def main():
    manifest = []
    failures = []

    for fname, url in SOURCES.items():
        out = RAW / fname
        result = fetch_one(url, out)
        record = {"file": str(out), "url": url, **result}
        manifest.append(record)
        if result["status"] == "failed":
            failures.append(record)

    (ART / "source_manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")

    # Do not fail the pipeline if source pages are blocked.
    # Priors are already encoded in config / computed_priors and fetch is best-effort only.
    if failures:
        print("Completed with fetch warnings:")
        for f in failures:
            print(f"- {f['url']} -> {f['error']}")
    else:
        print("Fetched all source pages successfully.")

if __name__ == "__main__":
    main()
