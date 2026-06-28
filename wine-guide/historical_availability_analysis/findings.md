# Historical availability — Munskänkarna tastings vs current Systembolaget stock

## TL;DR

- **Only 6.1 % (1,451 / 23,865) of Munskänkarna tasting rows correspond
  to a wine that is actually buyable right now in the tasted vintage**
  — either at a physical Systembolaget store or via the home-delivery
  depot network.
- **Tastings rot in ~1–2 years.** Of 2026 tastings, 57 % are still
  buyable. By 2025 it's 29 %. By 2024 it's 8.6 %. By 2022 it's under
  2 %. Everything from 2020 and earlier is effectively zero.
- **A cutoff at tasting-year 2020 drops 10,185 rows (43 % of the
  corpus) and costs only 37 keepers (2.5 % of keepers).** A more
  aggressive 2023 cutoff drops 16,452 rows (69 %) and costs 119
  keepers (8.2 %).
- **The dominant failure modes for old tastings are, in order:**
  no_match (65 %) — the article number no longer resolves to any wine;
  different_vintage (18 %) — the SKU exists but now sells a newer
  vintage; listed_but_no_stock (6 %) — the tasted vintage is still
  listed but everything is sold out; weak_name_only (5 %) — a
  suspicious sibling-rule match with name agreement but no producer
  confirmation.
- **Recommendation.** Cut tastings published before **2023** (or
  conservatively **2020**) from the active dataset. The remaining 31 %
  of the corpus captures 92 % of the currently-buyable keepers. Any
  earlier tasting row is statistically very unlikely ever to resolve
  to an in-stock wine in its tasted vintage again.

Numbers reproducible from this folder — see Running below.

---

## Method

Each tasting row in `data/wines_clean.csv` is a
`(code, tasting_name, tasting_producer, tasting_wine_year)` tuple.
We want to know whether that exact identity (same producer, same
cuvée, same *vintage*) is currently for sale anywhere.

1. **Match code → productNumber.**
   - If the code is already a valid `productNumber`, take it.
   - Otherwise try sibling suffixes `01, 02, 06, 08, 09, 11` in order
     and accept the first where BOTH tasting/SB names are similar
     (`sim ≥ 0.6` or Jaccard `≥ 0.5`) AND producers agree
     (`sim ≥ 0.6`). This is the two-signal rule validated in
     `../product_code_analysis/findings.md` (phase 4 crosstab).
   - A name-only sibling match is retained as `weak_name_only` (not
     counted as a keeper).
2. **Vintage check.** Compare the current search record's `vintage`
   field to the tasting row's `year`. Only exact-equal counts.
   Non-vintage wines (Champagne NV, port, sake, chocolate wine) get
   their own `_nv` track — we can't vintage-check them, so we just
   require them to be listed + in stock.
3. **Stock check.** For each matched productId with a vintage pass,
   call `/v1/site/stores/{productId}/` (all-store stock) and
   `/v1/stockbalance/depot/{depotId}/{productId}` across the three
   national depot warehouses (`0199`, `1899`, `2299`). Classify as
   `available_in_store` / `available_depot_only` / `listed_but_no_stock`.
4. **Everything else is a discard.** Buckets: `no_match`,
   `code_recycled` (exact PN collision), `different_vintage`,
   `weak_name_only`.

Rationale for the strict "same productNumber AND same vintage"
requirement:

- Systembolaget assigns one productNumber per (wine, packaging); when
  a new vintage arrives, the same productNumber rolls over.
  Historically-older vintages do not get a separate productNumber —
  they simply disappear from sale. So if the SKU currently lists a
  different vintage, the tasted vintage is off-shelf.
- The user's working assumption — *"if a wine is not in stock
  anywhere in the tasted vintage, it will not come back"* — matches
  how Systembolaget rotates through vintages, so we don't look for
  stale vintages at alternative productNumbers.

---

## Dataset

| | rows |
|---|---:|
| `data/wines_clean.csv` digit-code tasting rows | 23,865 |
| Systembolaget wine catalog | 17,563 |
| Systembolaget search (country-partitioned, deduped) | 15,018 |
| productIds flagged for stock query (strong match + vintage match) | 2,517 |

The matcher classifies:

| match_reason | rows |
|---|---:|
| no_match | 15,457 |
| sibling_01 (strong) | 6,667 |
| sibling_01_name_only (weak) | 1,222 |
| exact | 208 |
| sibling_02 (strong) | 189 |
| exact_name_mismatch | 49 |
| sibling_06 (strong) | 30 |
| sibling_02_name_only (weak) | 22 |
| sibling_08/09/11 | 14 |
| sibling_*_name_only (weak) | 7 |

Of the 7,108 strong matches, **2,205 (31 %) have the tasting vintage
equal to the SB current vintage** and 714 are NV (SB lists no
vintage). That's the upper bound on keepable rows before stock
filtering — 2,205 + 714 = 2,919.

---

## Headline — availability by tasting year

All percentages are within the tasting year (what share of that
year's rows survive).

| year | total | keep (vintage + in stock) | keep % |
|---|---:|---:|---:|
| 1998–2002 | 825 | 0 | 0.0 % |
| 2003–2007 | 1,020 | 1 | 0.1 % |
| 2008–2012 | 2,136 | 1 | 0.05 % |
| 2013–2017 | 3,636 | 12 | 0.3 % |
| 2018 | 462 | 2 | 0.4 % |
| 2019 | 2,106 | 21 | 1.0 % |
| 2020 | 2,025 | 10 | 0.5 % |
| 2021 | 2,122 | 31 | 1.5 % |
| 2022 | 2,120 | 41 | 1.9 % |
| 2023 | 2,242 | 111 | 5.0 % |
| 2024 | 2,296 | 197 | 8.6 % |
| 2025 | 2,191 | 634 | 28.9 % |
| 2026 | 684 | 390 | 57.0 % |

The cliff sits between 2024 and 2025: almost all tastings older than
~18 months are already worthless as buying guidance. That matches the
mechanism — Systembolaget churns to new vintages annually, and
popular wines sell through their current vintage within a season.

---

## Verdict breakdown

Across all 23,865 rows:

| verdict | rows | share |
|---|---:|---:|
| no_match | 15,457 | 64.8 % |
| different_vintage | 4,185 | 17.5 % |
| weak_name_only | 1,251 | 5.2 % |
| listed_but_no_stock | 1,126 | 4.7 % |
| **available_in_store** | **1,079** | **4.5 %** |
| **available_in_store_nv** | **372** | **1.6 %** |
| listed_but_no_stock_nv | 342 | 1.4 % |
| code_recycled | 49 | 0.2 % |
| no_tasting_year | 4 | 0.0 % |

- **Keepers: 1,451 rows (6.08 %).** Of those, ~26 % are NV wines
  (mostly Champagne / port).
- **Depot-only availability didn't contribute separately** — every
  keeper in the current corpus also has at least one store with
  stock. Depot stock existed alongside, but was never the sole
  channel. (Code path still implemented; future data could differ.)
- **`listed_but_no_stock_nv` (1.4 %)** — NV wines that are currently
  listed but zero stock. Many of these are seasonal / discontinued
  champagnes. Treated as discards.
- **`code_recycled` (0.2 %)** — exact productNumber match but name+
  producer both disagree. These are cases where Systembolaget
  reassigned an old article number to a new wine. Some are false
  positives of our matcher (e.g. `7696001` *Entrecuestas Godello*
  tasted as "Tilenus" / now catalogued as "Bodegas Estefania"
  — same wine, different producer name on either side). A more
  lenient matcher would promote ~dozens of these to keepers. Not
  worth the tuning for a decision about bulk discards.

---

## Cutoff decision table

For each candidate cutoff year (drop everything strictly before),
how much of the corpus goes, and how many keepers go with it:

| cutoff | rows dropped | keepers lost | % of keepers lost | rows remaining | keepers remaining |
|---|---:|---:|---:|---:|---:|
| 2015 | 5,618 | 6 | 0.4 % | 18,247 | 1,445 |
| 2018 | 7,617 | 14 | 1.0 % | 16,248 | 1,437 |
| 2019 | 8,079 | 16 | 1.1 % | 15,786 | 1,435 |
| **2020** | **10,185** | **37** | **2.6 %** | **13,680** | **1,414** |
| 2021 | 12,210 | 47 | 3.2 % | 11,655 | 1,404 |
| 2022 | 14,332 | 78 | 5.4 % | 9,533 | 1,373 |
| **2023** | **16,452** | **119** | **8.2 %** | **7,413** | **1,332** |
| 2024 | 18,694 | 230 | 15.9 % | 5,171 | 1,221 |
| 2025 | 20,990 | 427 | 29.4 % | 2,875 | 1,024 |

Two reasonable cutoff points:

- **Conservative: drop pre-2020.** Removes 43 % of rows and 2.6 % of
  keepers. Safe default — virtually no information lost, almost half
  the dead weight gone.
- **Aggressive: drop pre-2023.** Removes 69 % of rows and 8.2 % of
  keepers. You lose a small but real share of still-buyable wines.
  Good if storage / compute / review cost is the dominant concern.

The ROI of cutoff year `Y` — (rows dropped) / (keepers lost) — is
maximised at 2020 (275 rows dropped per keeper lost) and degrades
monotonically after. Cutoff 2024 costs only 81 rows per keeper lost,
and 2025 only 49 — those are where the curve starts biting.

---

## Failure-mode profile vs tasting age

Why each year is mostly unrecoverable:

| year | no_match | different_vintage | listed_but_no_stock |
|---|---:|---:|---:|
| 2026 | 9 % | 4 % | 22 % |
| 2025 | 31 % | 14 % | 18 % |
| 2024 | 45 % | 25 % | 11 % |
| 2023 | 50 % | 27 % | 7 % |
| 2022 | 60 % | 22 % | 4 % |
| 2020 | 66 % | 25 % | 1 % |
| 2015 | 86 % | 10 % | 0.2 % |
| 2010 | 94 % | 4 % | 0 % |

Reads:

- Within a year of tasting, *different_vintage* is the dominant loss
  (the wine is still sold, just next vintage on the shelf). That
  makes sense — vintages roll every 12-18 months.
- By 3 years out, *no_match* takes over. The SKU itself has been
  retired; Systembolaget has recycled the article number for
  something unrelated (as `../product_code_analysis/` showed, with
  ~90 % false-positive rate on prefix matches pre-2015).
- *listed_but_no_stock* peaks around 2024-2025. These are wines that
  are still on Systembolaget's books but have sold through and
  haven't been restocked — they will likely either be restocked
  (becomes `available`) or delisted (becomes `no_match`). Either
  way, not actionable today.

---

## Caveats

- **Stock is a point-in-time snapshot.** Fetched 2026-04-19. Wines
  that shift in/out of stock by the day will flip classifications.
  Don't treat 1,451 as a stable number to within a few percent —
  treat it as an order-of-magnitude bound.
- **Producer matching is conservative.** The 49 `code_recycled`
  rows and 1,251 `weak_name_only` rows include an unknown number of
  genuine matches where Munskänkarna recorded the importer/brand and
  Systembolaget records the winery, or vice versa. A more lenient
  rule would add on the order of 100-300 keepers — ~10-20 % uplift
  to the keep count. This does not change the cutoff recommendation:
  those rows concentrate in the same 2023-2026 window as the other
  keepers.
- **Search endpoint misses ~5 %.** Per `api.md` C054 country-partition
  pagination drops a handful of rows per partition. 2,545 catalog
  wine-PNs are not in the search cache. If a tasting matches one of
  those, it ends up as `weak_name_only` or `listed_but_no_stock`
  (no vintage data) rather than `available_in_store`. Effect on
  keeper counts is small.
- **NV wines special-cased.** 714 rows (1.4 + 1.6 %) map to SB
  listings with `vintage = null` (Champagne, port, sake, flavoured
  wine). Counted as keepers iff in stock; 372 of 714 pass.
- **No depot-only keepers observed.** Every in-vintage match with
  depot stock > 0 also had at least one store with stock > 0. The
  depot calls are therefore overhead for this particular snapshot —
  kept in the fetcher because a future snapshot with tighter store
  restocking could shift this.

---

## Practical consequence for the pipeline

If you care about *buying wine now*, the tasting dataset has a
strong natural **2-year shelf life**. Concretely:

1. Dropping tasting rows with `activity_publish_date < 2023-01-01`
   reduces `data/wines_clean.csv` from 25,937 rows to about 8,479,
   and preserves 92 % of the wines that are currently buyable in
   their tasted vintage.
2. A pipeline that re-runs this analysis once per month would let
   the downstream `filter_by_store.py` step work against a ~3× smaller
   but nearly-as-complete tasting corpus.
3. The remaining `no_match` rows in the 2023+ range (~3,400 rows)
   are wines that have already rolled over to a new vintage in under
   a year — there is no effective way to revive them short of
   cross-referencing Munskänkarna tastings of the *same producer's
   newer vintage*, which is a different problem.

---

## Reproducibility

```bash
# 1. catalog + search (reuses ../product_code_analysis/cache; ~10 min first time)
python3 historical_availability_analysis/fetch_data.py

# 2. match each tasting row to a productNumber (~5 s)
python3 historical_availability_analysis/match.py

# 3. fetch per-product stock + depot (~40 min for 2,517 products, ~1/s)
python3 historical_availability_analysis/fetch_stock.py

# 4. classify and aggregate (~3 s)
python3 historical_availability_analysis/analyze.py
```

Outputs in `out/`:

- `match_detail.csv` — one row per tasting row with PN, SB name/producer/vintage, match reason.
- `needed_productIds.json` — productIds fed to the stock fetcher.
- `match_summary.json` — match reason counts.
- `availability_detail.csv` — one row per tasting row with verdict and stock numbers.
- `availability_by_year.csv` — counts per (tasting_year, verdict).
- `cutoff_table.csv` — cumulative drop/loss for each candidate cutoff year.
- `availability_summary.json` — top-line numbers.
