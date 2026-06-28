"""
fetch_data.py  -  Cache all Systembolaget data we need for product-code analysis.

Writes:
  cache/catalog.json      - full /v1/product response (all SKUs, sparse fields)
  cache/wine_search.json  - deduped list of every wine from /v1/productsearch/search,
                            paginated per country to work around the 10k ES cap.

Re-runnable and idempotent: each step skips if the output already exists.
Use `--force` to refetch.
"""

import argparse
import json
import os
import sys
import time
from pathlib import Path

import requests

API_BASE = "https://api-extern.systembolaget.se"
API_KEY = "8d39a7340ee7439f8b4c1e995c8f3e4a"

HEADERS = {
    "Ocp-Apim-Subscription-Key": API_KEY,
    "Origin": "https://www.systembolaget.se",
    "Accept": "application/json",
    "User-Agent": "wine-guide-code-analysis/1.0",
}

CACHE = Path(__file__).parent / "cache"
CATALOG_PATH = CACHE / "catalog.json"
SEARCH_PATH = CACHE / "wine_search.json"


def session():
    s = requests.Session()
    s.headers.update(HEADERS)
    return s


def fetch_catalog(s):
    print("[catalog] fetching /v1/product ...", file=sys.stderr)
    r = s.get(f"{API_BASE}/sb-api-ecommerce/v1/product", timeout=120)
    r.raise_for_status()
    data = r.json()
    print(f"[catalog] got {len(data)} items", file=sys.stderr)
    return data


def fetch_country(s, country, max_pages=400, sleep=0.1):
    """Paginate wine search for a single country. Returns raw product dicts (deduped by productNumber)."""
    seen = {}
    page = 1
    total_pages = None
    while page <= max_pages:
        params = {"categoryLevel1": "Vin", "country": country, "page": page}
        r = s.get(
            f"{API_BASE}/sb-api-ecommerce/v1/productsearch/search",
            params=params,
            timeout=60,
        )
        r.raise_for_status()
        body = r.json()
        if total_pages is None:
            total_pages = body["metadata"]["totalPages"]
            doc_count = body["metadata"]["docCount"]
            print(f"  {country}: docCount={doc_count}, totalPages={total_pages}",
                  file=sys.stderr)
        products = body.get("products", [])
        if not products:
            break
        for p in products:
            pn = p.get("productNumber")
            if pn and pn not in seen:
                seen[pn] = p
        if page >= total_pages:
            break
        page += 1
        if sleep:
            time.sleep(sleep)
    return list(seen.values())


def fetch_all_wines(s):
    # 1) Get country filter list from a generic wine query.
    r = s.get(
        f"{API_BASE}/sb-api-ecommerce/v1/productsearch/search",
        params={"categoryLevel1": "Vin", "page": 1},
        timeout=60,
    )
    r.raise_for_status()
    body = r.json()
    filters = {f["name"]: f for f in body.get("filters", [])}
    country_modifiers = filters["Country"]["searchModifiers"]
    # Sort descending by count so the heavy partitions come first (fail fast).
    country_modifiers.sort(key=lambda m: -m.get("count", 0))
    total_doc = body["metadata"]["docCount"]
    print(f"[search] global docCount={total_doc}; "
          f"paginating {len(country_modifiers)} country partitions",
          file=sys.stderr)

    all_products = {}
    for m in country_modifiers:
        country = m["value"]
        expected = m.get("count", 0)
        products = fetch_country(s, country)
        for p in products:
            pn = p.get("productNumber")
            if pn and pn not in all_products:
                all_products[pn] = p
        print(f"  -> {country}: collected {len(products)} "
              f"(expected ~{expected}); running total={len(all_products)}",
              file=sys.stderr)
    # Wines with country=null won't be in any country partition. Catch them by
    # querying without the country filter as a safety net (limited to 10k cap,
    # but we've already covered the bulk).
    print("[search] fetching the (non-country-filtered) tail", file=sys.stderr)
    page = 1
    while True:
        r = s.get(
            f"{API_BASE}/sb-api-ecommerce/v1/productsearch/search",
            params={"categoryLevel1": "Vin", "page": page},
            timeout=60,
        )
        r.raise_for_status()
        b = r.json()
        prods = b.get("products", [])
        if not prods:
            break
        new = 0
        for p in prods:
            pn = p.get("productNumber")
            if pn and pn not in all_products:
                all_products[pn] = p
                new += 1
        if page == 1:
            print(f"  unfiltered: docCount={b['metadata']['docCount']} "
                  f"totalPages={b['metadata']['totalPages']}",
                  file=sys.stderr)
        if page >= b["metadata"]["totalPages"]:
            break
        page += 1
        time.sleep(0.1)

    print(f"[search] final unique productNumber count: {len(all_products)}",
          file=sys.stderr)
    return list(all_products.values())


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--skip-catalog", action="store_true")
    ap.add_argument("--skip-search", action="store_true")
    args = ap.parse_args()

    CACHE.mkdir(parents=True, exist_ok=True)
    s = session()

    if not args.skip_catalog and (args.force or not CATALOG_PATH.exists()):
        cat = fetch_catalog(s)
        CATALOG_PATH.write_text(json.dumps(cat))
        print(f"[catalog] wrote {CATALOG_PATH}", file=sys.stderr)
    else:
        print(f"[catalog] using cached {CATALOG_PATH}", file=sys.stderr)

    if not args.skip_search and (args.force or not SEARCH_PATH.exists()):
        wines = fetch_all_wines(s)
        SEARCH_PATH.write_text(json.dumps(wines))
        print(f"[search] wrote {SEARCH_PATH}", file=sys.stderr)
    else:
        print(f"[search] using cached {SEARCH_PATH}", file=sys.stderr)


if __name__ == "__main__":
    main()
