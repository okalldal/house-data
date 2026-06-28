# historical_availability_analysis

Meta-analysis of the Munskänkarna tasting database (`data/wines_clean.csv`)
against the current Systembolaget catalog + stock: **what fraction of
each tasting year can we still actually buy, in the tasted vintage, at
any Systembolaget store or via home delivery?**

Takes the matching conclusions from `../product_code_analysis/` as a
starting point and layers live stock data on top. The outcome is a
decision-support table for picking a cutoff year below which tasting
rows can be discarded wholesale.

See [`findings.md`](findings.md) for the write-up.

## Pipeline

```
historical_availability_analysis/
├── fetch_data.py          ensures catalog + search cache exists
│                          (delegates to ../product_code_analysis/fetch_data.py)
├── match.py               matches each tasting row to a productNumber
│                          using exact + sibling rules and the two-signal
│                          verification from product_code_analysis
├── fetch_stock.py         fetches all-store stock + depot stock for the
│                          unique productIds that passed vintage match
├── analyze.py             classifies each tasting row and aggregates
│                          by tasting year
├── cache/
│   ├── stock_by_productId.json     (owned)
│   └── depot_ids.json              (owned; catalog+search live in the
│                                   sibling folder's cache/)
└── out/
    ├── match_detail.csv            per-row match verdict
    ├── match_summary.json
    ├── needed_productIds.json      feeds fetch_stock
    ├── availability_detail.csv     per-row final verdict
    ├── availability_by_year.csv    aggregate
    ├── cutoff_table.csv            cumulative view for a cutoff decision
    └── availability_summary.json
```

## Running it

```bash
# From repo root. Uses catalog + search cache from product_code_analysis;
# will fetch that (~10 min) if not yet cached.
python3 historical_availability_analysis/fetch_data.py
python3 historical_availability_analysis/match.py

# Fetches stock for each candidate productId (~650 KB / product,
# ~0.5 s / product). Re-runnable; skips productIds already cached.
python3 historical_availability_analysis/fetch_stock.py

python3 historical_availability_analysis/analyze.py
```

## Classification buckets

Per tasting row, mutually exclusive, priority order:

| verdict | meaning |
|---|---|
| `no_match` | Tasting code does not resolve to any current productNumber (not as-is, not via sibling suffixes). |
| `code_recycled` | Code IS a valid productNumber but name+producer disagree — the SKU was reassigned. |
| `weak_name_only` | Sibling candidate matches on name but not producer — low confidence. |
| `no_tasting_year` | Row has no recorded year; cannot check vintage. |
| `different_vintage` | Code resolves, name+producer agree, but the SKU currently sells a DIFFERENT vintage. Tasted vintage is off-shelf. |
| `no_sb_vintage` / `…_nv` | SB listing carries no vintage (NV champagne, port). Bucketed separately. |
| `listed_but_no_stock` | Match + same vintage + zero stock anywhere. |
| `available_depot_only` | Match + same vintage + home-delivery only. |
| `available_in_store` | Match + same vintage + at least one physical store. |

`available_*` are the KEEPERS. Everything else is a discard candidate.
