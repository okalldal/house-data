# CLAUDE.md

Working notes for this project so we don't have to repeat ourselves.

## What this project is

Wine-value research: combine Munskänkarna tasting notes with Systembolaget's
current product catalog to find good-value wines at specific stores.

## Data sources and their roles

- **Systembolaget API** is authoritative for *product* facts: product number,
  bottle volume, current price, current vintage sold, stock at a given store.
- **`data/wines_clean.csv` (Munskänkarna Vinlocus)** is authoritative for
  *quality* only. Its `price`, `volume`, `year` reflect the tasting
  event, not what Systembolaget currently sells. Never use those fields
  for ranking or value calculations — always re-fetch from the API.

## Repo layout

- **Shared library** `lib/` — imported by every root script:
  - `lib/matching.py` — `match_row()` maps a Munskänkarna tasting row to a
    Systembolaget `productNumber` using name + producer similarity and the
    sibling-suffix fallback (01/02/06/08/09/11).
  - `lib/sb_api.py` — thin wrappers around the documented endpoints
    (`session`, `fetch_catalog`, `fetch_all_wines`, `fetch_all_store_stock`,
    `fetch_single_store_stock`, `fetch_depot_stock`, `fetch_postal_code`,
    `fetch_stores`, `discover_depot_ids`).
  - `lib/cache.py` — JSON and gzipped-JSON atomic writes, TTL helper,
    conventional paths under `cache/` and `data/`.
- **Pipeline scripts at the repo root** (run in this order):
  1. `scrape_wines.py` → `data/wines.csv`
  2. `clean_wines.py` → `data/wines_clean.csv`
  3. `build_catalog.py` → `cache/catalog.json`, `cache/wine_search.json`
  4. `list_stores.py --refresh` → `cache/stores.json`
  5. `match_wines.py` → `data/wines_matched.csv`
  6. `refresh_stock.py` → `cache/stock/<productId>.json.gz` (hybrid
     prefetch: only points ≥ 15 by default; the rest fill in on-demand
     via `find_wines.py --on-demand`)
  7. `find_wines.py` — rank by availability at a store / postcode / depot.
- `data/` — CSV artefacts: `wines.csv`, `wines_clean.csv`, `wines_matched.csv`.
- `cache/` — Systembolaget artefacts. `stock/*.json.gz` is one file per
  productId; everything else is a single JSON file.
- `product_code_analysis/` and `historical_availability_analysis/` —
  original research subprojects that informed the matching + availability
  algorithms. Kept as historical records; superseded by `lib/matching.py`
  and the root pipeline.
- `api-docs/systembolaget/` and `api-docs/munskankarna/` — per-API
  documentation. Each subtree contains:
  - `api.md` — **start here** for API guidance: endpoints, parameters,
    response shapes. Read this whenever you need to understand how to use
    an API.
  - `STRATEGY.md` and `tests/` probes — **only consult these** when
    `api.md` is insufficient: the behaviour is undocumented, a claim seems
    wrong, or you need to run a live probe to verify something. Each subtree
    owns its own claim IDs (`C###` for Systembolaget, `M###` for
    Munskänkarna). Run `pytest` from the repo root to execute the probes.

## Wine identity rules

- **Different vintages = different wines.** Never pool, average, or otherwise
  combine ratings across vintages of the same SKU. `find_wines.py` enforces
  this by default via `--vintage-match strict` — a tasting is only a match
  if the currently-stocked vintage equals the tasted vintage.
- `systembolaget_id` in the tasting DB is often a short 4–5 digit article
  number. The same short id can span multiple vintages and bottle sizes, each
  with its own 6+ digit `productNumber` (e.g. `4151` → `415101` for one
  packaging, `415102` for another). Canonical product identity is the
  `productNumber` from the API.
- Old 5-digit article numbers typically map to the catalog by appending a
  suffix (e.g. `90455` → `9045501`), though the suffix varies by bottle size
  and packaging — `lib/matching.py::match_row` handles the lookup.

## Postcode / home delivery

- `lib.sb_api.fetch_postal_code(postcode)` resolves a 5-digit customer
  postcode to `{homeOrderApplicable, depotStockId, postalCity, ...}`.
- The returned `depotStockId` is the same identifier space as
  `store.depotStockId` in the all-store stock response, and it can be
  passed straight to `/v1/stockbalance/depot/{depotId}/{productId}`.
- `find_wines.py --orderable-to-postcode 11454` uses this to answer "is
  this wine orderable to my door?" without depending on store-level stock.
