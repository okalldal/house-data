"""
refresh_stock.py  —  Populate cache/stock/<productId>.json.gz.

Two modes:

  Bulk prefetch (default)      — for every matched productId whose
                                  points >= --prefetch-min-points, fetch
                                  all-store stock + depot stock and cache.
                                  Honour --max-age-hours (default 24): skip
                                  entries that are still fresh.

  On-demand single-store       — given --product-ids P,Q and --site-ids
                                  A,B, fetch (P,A),(P,B),(Q,A),(Q,B) via
                                  the single-store endpoint and merge into
                                  the existing cache file for each product.
                                  Used by find_wines.py to fill stock for
                                  wines that weren't prefetched.

Gzipped JSON on disk. Each cache file has shape:

  {
    "productId": "...",
    "storeStocks": [ ... (filtered) ... ],   # partial in on-demand mode
    "depot_stock":  {"0199": 10, "1899": 37, "2299": 26},
    "fetched_at": "2026-04-20T19:30:00+00:00",
    "all_store_fetched": true,               # False if only single-store calls
  }
"""

import argparse
import csv
import sys
import time
from datetime import datetime, timezone

import requests

from lib import cache as _c
from lib import sb_api

DEFAULT_PREFETCH_MIN_POINTS = 15.0
DEFAULT_SLEEP_S = 0.05


def _read_cache(product_id):
    path = _c.stock_path(product_id)
    if path.exists():
        try:
            return _c.read_json_gz(path)
        except Exception:
            return None
    return None


def _trim_store_stocks(store_stocks):
    """Keep only the fields downstream scripts consume — cuts ~60% of bytes."""
    trimmed = []
    for e in store_stocks:
        store = e.get("store") or {}
        sb = e.get("stockBalance") or {}
        trimmed.append({
            "store": {
                "siteId": store.get("siteId"),
                "alias": store.get("alias"),
                "displayName": store.get("displayName") or store.get("alias"),
                "address": store.get("address"),
                "city": store.get("city"),
                "county": store.get("county"),
                "postalCode": store.get("postalCode"),
                "isBlocked": store.get("isBlocked"),
                "depotStockId": store.get("depotStockId"),
            },
            "stockBalance": {
                "stock": sb.get("stock") or 0,
                "shelf": sb.get("shelf"),
            },
        })
    return trimmed


def _load_matched_products(path):
    rows = []
    with open(path, encoding="utf-8") as f:
        for r in csv.DictReader(f):
            pid = (r.get("productId") or "").strip()
            if not pid:
                continue
            try:
                pts = float(r.get("points") or 0)
            except ValueError:
                pts = 0.0
            rows.append((pid, pts, r.get("match_reason", ""), r))
    return rows


def _dedupe_products(rows, min_points=None):
    """Return (product_id → max_points) for rows passing min_points."""
    seen = {}
    for pid, pts, reason, _r in rows:
        if min_points is not None and pts < min_points:
            continue
        if reason.endswith("_name_only") or reason == "exact_name_mismatch":
            continue
        if pid not in seen or pts > seen[pid]:
            seen[pid] = pts
    return seen


def ensure_depot_ids(s):
    if _c.DEPOT_IDS_PATH.exists():
        try:
            cached = _c.read_json(_c.DEPOT_IDS_PATH)
            if cached:
                return cached
        except Exception:
            pass
    # Use a seed from the first wine in cache/wine_search.json.
    wines = _c.read_json(_c.WINE_SEARCH_PATH)
    seed_ids = [w["productId"] for w in wines[:20] if w.get("productId")]
    depots = sb_api.discover_depot_ids(s, seed_ids)
    _c.write_json(_c.DEPOT_IDS_PATH, depots)
    return depots


def fetch_and_cache_all_store(s, product_id, depot_ids, sleep_s):
    body = sb_api.fetch_all_store_stock(s, product_id)
    if body is None:
        cache = {
            "productId": product_id,
            "storeStocks": [],
            "depot_stock": {d: 0 for d in depot_ids},
            "fetched_at": _c.now_utc_iso(),
            "all_store_fetched": True,
            "not_found": True,
        }
        _c.write_json_gz(_c.stock_path(product_id), cache)
        return cache

    depot_stock = {}
    for did in depot_ids:
        try:
            d = sb_api.fetch_depot_stock(s, did, product_id)
            depot_stock[did] = (d or {}).get("stock") or 0
        except requests.HTTPError:
            depot_stock[did] = 0
        if sleep_s:
            time.sleep(sleep_s)

    cache = {
        "productId": product_id,
        "storeStocks": _trim_store_stocks(body.get("storeStocks", [])),
        "depot_stock": depot_stock,
        "fetched_at": _c.now_utc_iso(),
        "all_store_fetched": True,
    }
    _c.write_json_gz(_c.stock_path(product_id), cache)
    return cache


def bulk_prefetch(args):
    rows = _load_matched_products(_c.WINES_MATCHED_CSV)
    targets = _dedupe_products(rows, min_points=args.prefetch_min_points)
    print(f"[stock] prefetch candidates: {len(targets)} productIds "
          f"(points >= {args.prefetch_min_points})", file=sys.stderr)

    s = sb_api.session()
    depot_ids = ensure_depot_ids(s)
    print(f"[stock] depot ids: {depot_ids}", file=sys.stderr)

    todo = []
    for pid in targets:
        path = _c.stock_path(pid)
        if args.force or not _c.is_fresh(path, args.max_age_hours):
            todo.append(pid)
    print(f"[stock] fetching {len(todo)} (cached fresh: {len(targets)-len(todo)})",
          file=sys.stderr)

    t0 = time.time()
    errors = 0
    for i, pid in enumerate(todo, 1):
        try:
            fetch_and_cache_all_store(s, pid, depot_ids, args.sleep)
        except requests.HTTPError as e:
            print(f"[stock] {pid}: {e}", file=sys.stderr)
            errors += 1
        if args.sleep:
            time.sleep(args.sleep)
        if i % 50 == 0 or i == len(todo):
            rate = i / (time.time() - t0 + 1e-9)
            eta = (len(todo) - i) / rate if rate else 0
            print(f"[stock] {i}/{len(todo)} (rate {rate:.1f}/s, ETA {eta/60:.1f} min)",
                  file=sys.stderr)
    print(f"[stock] done. errors={errors}", file=sys.stderr)


def on_demand_single_store(product_ids, site_ids, sleep_s=DEFAULT_SLEEP_S):
    """For each (productId, siteId) pair fetch single-store stock and
    merge into that product's cache file. Preserves any existing data."""
    s = sb_api.session()
    for pid in product_ids:
        existing = _read_cache(pid) or {
            "productId": pid,
            "storeStocks": [],
            "depot_stock": {},
            "fetched_at": _c.now_utc_iso(),
            "all_store_fetched": False,
        }
        existing_by_site = {
            (e.get("store") or {}).get("siteId"): e
            for e in existing.get("storeStocks", [])
        }
        for sid in site_ids:
            try:
                body = sb_api.fetch_single_store_stock(s, sid, pid)
            except requests.HTTPError as e:
                print(f"[stock] {pid}/{sid}: {e}", file=sys.stderr)
                body = None
            stock = (body or {}).get("stock") or 0
            entry = existing_by_site.get(sid)
            if entry is None:
                entry = {
                    "store": {"siteId": sid},
                    "stockBalance": {"stock": stock,
                                     "shelf": (body or {}).get("shelf")},
                }
                existing["storeStocks"].append(entry)
                existing_by_site[sid] = entry
            else:
                entry["stockBalance"]["stock"] = stock
                entry["stockBalance"]["shelf"] = (body or {}).get("shelf")
            if sleep_s:
                time.sleep(sleep_s)
        existing["fetched_at"] = _c.now_utc_iso()
        _c.write_json_gz(_c.stock_path(pid), existing)


def refresh_depot_for_postcode(postcode, product_ids, sleep_s=DEFAULT_SLEEP_S):
    """Ensure depot stock for the depot serving `postcode` is present in
    each product's cache file. Returns the depotId or None if the postcode
    is not served. Used by find_wines.py --orderable-to-postcode."""
    s = sb_api.session()
    body = sb_api.fetch_postal_code(s, postcode)
    if not body or not body.get("homeOrderApplicable"):
        return None
    depot_id = body["depotStockId"]
    for pid in product_ids:
        existing = _read_cache(pid)
        if existing is None:
            continue
        depot_stock = existing.setdefault("depot_stock", {})
        if depot_id in depot_stock:
            continue
        try:
            d = sb_api.fetch_depot_stock(s, depot_id, pid)
            depot_stock[depot_id] = (d or {}).get("stock") or 0
        except requests.HTTPError:
            depot_stock[depot_id] = 0
        _c.write_json_gz(_c.stock_path(pid), existing)
        if sleep_s:
            time.sleep(sleep_s)
    return depot_id


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--force", action="store_true",
                    help="refetch even if cache is fresh")
    ap.add_argument("--max-age-hours", type=float, default=24.0,
                    help="a cache file younger than this is considered fresh")
    ap.add_argument("--prefetch-min-points", type=float,
                    default=DEFAULT_PREFETCH_MIN_POINTS,
                    help="only prefetch wines with points >= this (default 15)")
    ap.add_argument("--sleep", type=float, default=DEFAULT_SLEEP_S,
                    help="sleep between HTTP calls (seconds)")
    ap.add_argument("--product-ids",
                    help="comma-separated productIds (on-demand mode)")
    ap.add_argument("--site-ids",
                    help="comma-separated siteIds (on-demand mode)")
    args = ap.parse_args()

    if args.product_ids and args.site_ids:
        pids = [p.strip() for p in args.product_ids.split(",") if p.strip()]
        sids = [s.strip() for s in args.site_ids.split(",") if s.strip()]
        print(f"[stock] on-demand: {len(pids)} products × {len(sids)} stores",
              file=sys.stderr)
        on_demand_single_store(pids, sids, sleep_s=args.sleep)
        return

    bulk_prefetch(args)


if __name__ == "__main__":
    main()
