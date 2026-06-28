# product_code_analysis

Self-contained study of how Munskänkarna's `systembolaget_id` codes
relate to Systembolaget's current `productNumber` space. Answers the
questions:

- How many tasting codes are valid `productNumber`s right now?
- For those that are, do they still refer to the same wine?
- For those that aren't, does the "append `01`" sibling rule work?
- How often does the sibling rule map to a completely unrelated wine
  (false positive), and why?

## Results

See [`findings.md`](findings.md) for the full write-up with numbers
and samples. Short version:

- **1.1 %** of tasting codes are direct `productNumber` matches.
- For the other 99 %, appending `01` reaches a current SKU **75 %**
  of the time — and **about half of those reach-alikes are the wrong
  wine**, because Systembolaget recycles article numbers.
- The false-positive rate scales almost linearly with tasting age:
  ~0 % for 2026 tastings, ~90 % for pre-2015 tastings.
- **There is no server-side "same wine?" signal.** Verifying a match
  requires fuzzy comparison of `productNameBold`/`productNameThin` +
  `producerName` from the search endpoint.

## Layout

```
fetch_data.py              Cache catalog + full per-country wine search
analyze_codes.py           Four-phase analysis, emits CSVs + JSON
cache/catalog.json         /v1/product response
cache/wine_search.json     Deduped search rows with vintage/producer/country
out/phase*.json            Per-phase summary
out/phase*_*.csv           Per-row details
out/summary.json           All top-line numbers together
findings.md                Write-up
```

## Running it

```bash
# From repo root. Fetch takes ~1 min for catalog + ~8 min for search.
python3 product_code_analysis/fetch_data.py

# Analysis takes ~10 s once the cache is warm.
python3 product_code_analysis/analyze_codes.py
```

Re-fetch with `--force`. Cache files are ~46 MB total so they're
checked in — skip `product_code_analysis/cache/` in git if you prefer
to refetch each time.
