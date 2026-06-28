"""
fetch_stock.py  -  Cache current Systembolaget stock for matched productIds.

For each productId the prior matching stage flagged as "worth checking"
(see out/needed_productIds.json), we:

  1. Call /v1/site/stores/{productId}/ once -> aggregates per-store stock
     and the set of depotStockIds.
  2. For each distinct depotId the network uses (discovered from any
     all-store response), call /v1/stockbalance/depot/{depotId}/{productId}
     -> home-delivery stock.

Per api.md C051 the depot set is small (handful of central warehouses),
so depot calls are cheap. All-store calls dominate the runtime.

Writes cache/stock_by_productId.json with one entry per productId:
  {
    "store_total": 42,           # sum of stock across all stores
    "stores_with_stock": 8,      # how many stores have stock > 0
    "store_count_total": 400,    # total stores the endpoint returned
    "depot_total": 31,           # sum across the national depot network
    "depot_by_id": {"1": 31, "2": 0, ...},
    "fetched": <ISO timestamp>
  }

Idempotent: re-running only fetches productIds not already in cache.
Use `--force` to re-fetch.
"""

import argparse
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import requests

ROOT = Path(__file__).parent
OUT = ROOT / "out"
CACHE = ROOT / "cache"
NEEDED = OUT / "needed_productIds.json"
STOCK_CACHE = CACHE / "stock_by_productId.json"
DEPOT_IDS_CACHE = CACHE / "depot_ids.json"

API_BASE = "https://api-extern.systembolaget.se"
API_KEY = "8d39a7340ee7439f8b4c1e995c8f3e4a"
HEADERS = {
    "Ocp-Apim-Subscription-Key": API_KEY,
    "Origin": "https://www.systembolaget.se",
    "Accept": "application/json",
    "User-Agent": "wine-guide-availability/1.0",
}


def session():
    s = requests.Session()
    s.headers.update(HEADERS)
    return s


def fetch_all_store_stock(s, product_id):
    r = s.get(f"{API_BASE}/sb-api-ecommerce/v1/site/stores/{product_id}/", timeout=60)
    if r.status_code == 404:
        return None
    r.raise_for_status()
    return r.json()


def fetch_depot_stock(s, depot_id, product_id):
    r = s.get(
        f"{API_BASE}/sb-api-ecommerce/v1/stockbalance/depot/{depot_id}/{product_id}",
        timeout=30,
    )
    if r.status_code == 404:
        return None
    r.raise_for_status()
    return r.json()


def discover_depot_ids(s, seed_product_id):
    """Probe one product to enumerate the depot network."""
    body = fetch_all_store_stock(s, seed_product_id)
    if not body:
        return []
    depots = set()
    for entry in body.get("storeStocks", []):
        did = (entry.get("store") or {}).get("depotStockId")
        if did:
            depots.add(str(did))
    return sorted(depots)


def summarise_store(body):
    stocks = body.get("storeStocks", []) if body else []
    total = 0
    with_stock = 0
    for e in stocks:
        sb = e.get("stockBalance") or {}
        n = sb.get("stock") or 0
        total += n
        if n > 0:
            with_stock += 1
    return total, with_stock, len(stocks)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--force", action="store_true", help="refetch all products")
    ap.add_argument("--sleep", type=float, default=0.05,
                    help="sleep between all-store calls")
    args = ap.parse_args()

    CACHE.mkdir(parents=True, exist_ok=True)
    if not NEEDED.exists():
        print(f"[error] {NEEDED} missing - run match.py first.", file=sys.stderr)
        sys.exit(1)
    needed = json.loads(NEEDED.read_text())
    print(f"[stock] target: {len(needed)} productIds", file=sys.stderr)

    cache = {}
    if STOCK_CACHE.exists() and not args.force:
        cache = json.loads(STOCK_CACHE.read_text())
        print(f"[stock] cache has {len(cache)} entries", file=sys.stderr)

    s = session()

    # Discover depot ids once.
    depot_ids = []
    if DEPOT_IDS_CACHE.exists() and not args.force:
        depot_ids = json.loads(DEPOT_IDS_CACHE.read_text())
    if not depot_ids:
        for pid in needed[:20]:
            depot_ids = discover_depot_ids(s, pid)
            if depot_ids:
                break
        DEPOT_IDS_CACHE.write_text(json.dumps(depot_ids))
    print(f"[stock] depot ids: {depot_ids}", file=sys.stderr)

    todo = [p for p in needed if p not in cache]
    print(f"[stock] fetching {len(todo)} new productIds", file=sys.stderr)

    # Periodic checkpoint so partial runs aren't lost.
    checkpoint_every = 50
    done = 0
    t0 = time.time()
    for pid in todo:
        try:
            body = fetch_all_store_stock(s, pid)
        except requests.HTTPError as e:
            print(f"[stock] {pid}: {e}", file=sys.stderr)
            body = None
        if body is None:
            cache[pid] = {
                "store_total": 0,
                "stores_with_stock": 0,
                "store_count_total": 0,
                "depot_total": 0,
                "depot_by_id": {},
                "all_store_missing": True,
                "fetched": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            }
        else:
            store_total, with_stock, store_count = summarise_store(body)
            depot_by_id = {}
            depot_total = 0
            for did in depot_ids:
                try:
                    d = fetch_depot_stock(s, did, pid)
                    n = (d or {}).get("stock") or 0
                except requests.HTTPError:
                    n = 0
                depot_by_id[did] = n
                depot_total += n
            cache[pid] = {
                "store_total": store_total,
                "stores_with_stock": with_stock,
                "store_count_total": store_count,
                "depot_total": depot_total,
                "depot_by_id": depot_by_id,
                "fetched": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            }
        done += 1
        if done % checkpoint_every == 0:
            STOCK_CACHE.write_text(json.dumps(cache))
            rate = done / (time.time() - t0 + 1e-9)
            eta_s = (len(todo) - done) / rate if rate else 0
            print(f"[stock] {done}/{len(todo)} "
                  f"(rate {rate:.1f}/s, ETA {eta_s/60:.1f} min)",
                  file=sys.stderr)
        if args.sleep:
            time.sleep(args.sleep)

    STOCK_CACHE.write_text(json.dumps(cache))
    print(f"[stock] done. cache size: {len(cache)}", file=sys.stderr)


if __name__ == "__main__":
    main()
