"""
Systembolaget api-extern client. Thin wrappers around the documented
endpoints — see api-docs/systembolaget/api.md.
"""

import time
from typing import Iterable

import requests


def _get_with_retries(s, url, *, max_tries=5, timeout=30, **kwargs):
    """GET with exponential backoff on 429/503 — the API occasionally rejects
    under concurrent load. Returns the response. Other statuses are returned
    as-is for callers to classify."""
    delay = 1.0
    for attempt in range(max_tries):
        r = s.get(url, timeout=timeout, **kwargs)
        if r.status_code not in (429, 503):
            return r
        if attempt == max_tries - 1:
            return r
        time.sleep(delay)
        delay *= 2
    return r  # unreachable

API_BASE = "https://api-extern.systembolaget.se"
API_KEY = "8d39a7340ee7439f8b4c1e995c8f3e4a"

HEADERS = {
    "Ocp-Apim-Subscription-Key": API_KEY,
    "Origin": "https://www.systembolaget.se",
    "Accept": "application/json",
    "User-Agent": "wine-guide/1.0",
}


def session() -> requests.Session:
    s = requests.Session()
    s.headers.update(HEADERS)
    return s


# --- Catalog + search ---------------------------------------------------------

def fetch_catalog(s: requests.Session):
    """GET /v1/product — sparse index of every SKU. ~7 MB."""
    r = s.get(f"{API_BASE}/sb-api-ecommerce/v1/product", timeout=120)
    r.raise_for_status()
    return r.json()


def _search_page(s, *, country=None, page=1, **extra):
    params = {"categoryLevel1": "Vin", "page": page}
    if country:
        params["country"] = country
    params.update(extra)
    r = s.get(
        f"{API_BASE}/sb-api-ecommerce/v1/productsearch/search",
        params=params,
        timeout=60,
    )
    r.raise_for_status()
    return r.json()


def fetch_country_wines(s, country, *, max_pages=400, sleep=0.1):
    """Paginate wine search for one country. Dedups locally by productNumber."""
    seen = {}
    page = 1
    total_pages = None
    while page <= max_pages:
        body = _search_page(s, country=country, page=page)
        if total_pages is None:
            total_pages = body["metadata"]["totalPages"]
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


def fetch_all_wines(s, *, sleep=0.1, on_country=None):
    """
    Fetch the entire wine search index by partitioning on the `country`
    filter (works around the ES 10k cap, per C035/C036), then sweeping the
    unfiltered tail for country=null wines.

    `on_country(name, expected, collected, running_total)` is an optional
    progress callback invoked after each partition.
    """
    body = _search_page(s, page=1)
    filters = {f["name"]: f for f in body.get("filters", [])}
    country_modifiers = filters["Country"]["searchModifiers"]
    country_modifiers.sort(key=lambda m: -m.get("count", 0))

    all_products: dict = {}
    for m in country_modifiers:
        country = m["value"]
        expected = m.get("count", 0)
        products = fetch_country_wines(s, country, sleep=sleep)
        for p in products:
            pn = p.get("productNumber")
            if pn and pn not in all_products:
                all_products[pn] = p
        if on_country:
            on_country(country, expected, len(products), len(all_products))

    # Catch country=null wines via an unfiltered sweep (within 10k cap).
    page = 1
    while True:
        b = _search_page(s, page=page)
        prods = b.get("products", [])
        if not prods:
            break
        for p in prods:
            pn = p.get("productNumber")
            if pn and pn not in all_products:
                all_products[pn] = p
        if page >= b["metadata"]["totalPages"]:
            break
        page += 1
        if sleep:
            time.sleep(sleep)

    return list(all_products.values())


# --- Stock --------------------------------------------------------------------

def fetch_all_store_stock(s, product_id):
    """GET /v1/site/stores/{productId}/ — all stores, one call (~650 KB)."""
    r = s.get(f"{API_BASE}/sb-api-ecommerce/v1/site/stores/{product_id}/", timeout=60)
    if r.status_code == 404:
        return None
    r.raise_for_status()
    return r.json()


def fetch_single_store_stock(s, site_id, product_id):
    """GET /v1/stockbalance/store/{siteId}/{productId} — one pair, ~1 KB."""
    r = s.get(
        f"{API_BASE}/sb-api-ecommerce/v1/stockbalance/store/{site_id}/{product_id}",
        timeout=30,
    )
    if r.status_code == 404:
        return None
    r.raise_for_status()
    return r.json()


def fetch_depot_stock(s, depot_id, product_id):
    """GET /v1/stockbalance/depot/{depotId}/{productId}."""
    r = s.get(
        f"{API_BASE}/sb-api-ecommerce/v1/stockbalance/depot/{depot_id}/{product_id}",
        timeout=30,
    )
    if r.status_code == 404:
        return None
    r.raise_for_status()
    return r.json()


def discover_depot_ids(s, seed_product_ids: Iterable[str]):
    """Probe a handful of products to enumerate the depot network.

    Stops as soon as one product returns a non-empty depot set.
    """
    for pid in seed_product_ids:
        body = fetch_all_store_stock(s, pid)
        if not body:
            continue
        depots = set()
        for entry in body.get("storeStocks", []):
            did = (entry.get("store") or {}).get("depotStockId")
            if did:
                depots.add(str(did))
        if depots:
            return sorted(depots)
    return []


# --- Store lookup -------------------------------------------------------------

def fetch_stores(s, q: str = ""):
    """GET /v1/sitesearch/site. Empty `q` returns the whole network (C074)."""
    r = s.get(
        f"{API_BASE}/sb-api-ecommerce/v1/sitesearch/site",
        params={"q": q, "includePredictions": "false"},
        timeout=60,
    )
    r.raise_for_status()
    return r.json()


# --- Postcode → home delivery -------------------------------------------------

def fetch_postal_code(s, postcode: str):
    """GET /v1/postalCode/{code}. Returns the dict on 200, None on 404, raises on 4xx/5xx.

    Retries on 429/503 — the API occasionally rate-limits under concurrent
    load (e.g. when a bulk prefetch is running in another process).
    """
    r = _get_with_retries(
        s,
        f"{API_BASE}/sb-api-ecommerce/v1/postalCode/{postcode}",
    )
    if r.status_code == 404:
        return None
    r.raise_for_status()
    return r.json()
