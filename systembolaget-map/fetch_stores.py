#!/usr/bin/env python3
"""
fetch_stores.py — Download the Systembolaget store network and write a compact
GeoJSON-ish JSON file for the interactive distance map.

Source: GET /sb-api-ecommerce/v1/sitesearch/site?q=  (the empty-q call returns
the whole network in one shot — see ../wine-guide/api-docs/systembolaget/api.md,
claim C074). Each record carries a `position` {latitude, longitude}, which is
all the map needs.

We keep only Systembolaget's own stores (isAgent == false); third-party agents
("ombud") are dropped because the "distance to nearest Systembolaget" question
is about real stores.

Output: data/stores.json
    {
      "generated": "<ISO date or null>",
      "count": <int>,
      "stores": [
        {"id","name","address","city","county","lat","lon"}, ...
      ]
    }

Usage:
    python3 fetch_stores.py
"""

import json
import sys
from pathlib import Path

import requests

API_BASE = "https://api-extern.systembolaget.se"
# Public frontend subscription key (visible in systembolaget.se DevTools).
# Mirrors ../wine-guide/lib/sb_api.py; refresh there if it ever rotates.
API_KEY = "8d39a7340ee7439f8b4c1e995c8f3e4a"

HEADERS = {
    "Ocp-Apim-Subscription-Key": API_KEY,
    "Origin": "https://www.systembolaget.se",
    "Accept": "application/json",
    "User-Agent": "systembolaget-map/1.0",
}

OUT_PATH = Path(__file__).parent / "data" / "stores.json"


def fetch_stores():
    r = requests.get(
        f"{API_BASE}/sb-api-ecommerce/v1/sitesearch/site",
        params={"q": "", "includePredictions": "false"},
        headers=HEADERS,
        timeout=60,
    )
    r.raise_for_status()
    return r.json().get("siteSearchResults", [])


def main():
    raw = fetch_stores()

    stores = []
    skipped_no_pos = 0
    for s in raw:
        if s.get("isAgent"):
            continue
        pos = s.get("position") or {}
        lat, lon = pos.get("latitude"), pos.get("longitude")
        if lat is None or lon is None:
            skipped_no_pos += 1
            continue
        stores.append({
            "id": s.get("siteId"),
            "name": s.get("displayName") or s.get("alias") or s.get("siteId"),
            "address": s.get("streetAddress"),
            "city": s.get("city"),
            "county": s.get("county"),
            "lat": round(float(lat), 6),
            "lon": round(float(lon), 6),
        })

    stores.sort(key=lambda x: (x["id"] or ""))

    out = {
        "source": "Systembolaget api-extern /v1/sitesearch/site",
        "count": len(stores),
        "stores": stores,
    }

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")

    print(f"[fetch_stores] {len(raw)} sites -> {len(stores)} real stores "
          f"({skipped_no_pos} dropped for missing coordinates)", file=sys.stderr)
    print(f"[fetch_stores] wrote {OUT_PATH}", file=sys.stderr)


if __name__ == "__main__":
    main()
