# Munskänkarna API — Verified Reference

Every claim on this page is backed by at least one probe in
`api-docs/munskankarna/tests/`. Claim tags like `[M001]` map to test
functions named `test_M001_...`. See `STRATEGY.md` (alongside this file)
for the research approach, and run
`pytest api-docs/munskankarna/tests/` from the repo root to re-verify
the whole document against the live API.

- **Base URL:** `https://www.munskankarna.se`
- **Auth:** none required. Send a polite `User-Agent`.

The winesearch API is an Umbraco surface-controller pair under
`/umbraco/surface/winesearch/`. It was reverse-engineered from
systembolaget-style DevTools traffic on the public Vinlocus search
page. Nothing here is contractually stable, but the shapes have been
consistent for the lifetime of this repo.

---

## Facets — `GET /umbraco/surface/winesearch/getfacets/`

Returns the complete filter catalog — every session key, country,
grape, producer, etc. that the Vinlocus search page can narrow by.
Used primarily to enumerate session keys for `listwinebottles/`.

- Returns HTTP 200 with a JSON body `[M001]`.
- Only GET is supported; POST returns HTTP 404 `[M002]`.
- Response is a JSON object with a single top-level key `facets`
  mapping to an object `[M003]`.
- `facets` exposes at least these ten categories `[M004]`:
  `categoryName`, `country`, `region`, `importer`, `rating`,
  `grapeTypes`, `price`, `producer`, `wineBottleActivityName`,
  `wineBottleActivityType`.
- Every facet entry is a JSON object with exactly the keys `item1`,
  `item2`, `item3`, `item4` — a generic C# tuple serialisation shared
  across all facet categories `[M005]`. `item1` is typically the
  human-readable label, `item2` is the filter token, `item3` is a
  parenthesised count (e.g. `"(17)"`), and `item4` is usually null.

### Session archive (`wineBottleActivityName`)

- Every `wineBottleActivityName[*].item2` is a string of the form
  `YYYYMMDD-<label>` (e.g. `"20260409-Hitlista 9 april 2026"`). This
  is the token to pass back as the `wineBottleActivityName[]`
  parameter on `listwinebottles/` `[M006]`.
- The facet enumerates the **full** historical session archive — at
  least several hundred sessions, growing as new tastings are
  published `[M007]`.

### Assortment buckets (`wineBottleActivityType`)

- `wineBottleActivityType[*].item1` includes at least the following
  high-level buckets, which roughly mirror Systembolaget's sourcing
  categories and Munskänkarna's own publication types `[M008]`:
  - `"Fast sortiment"` — permanent range
  - `"Tillfälligt sortiment"` — temporary range
  - `"Ordervaror på Systembolaget"` — advance-order only
  - `"Hitlista"` — editor's weekly picks
  - `"Temaprovning"` — themed tasting sessions

---

## Tasting notes — `POST /umbraco/surface/winesearch/listwinebottles/`

Returns the paginated stream of published tasting notes ("wine
bottles"). This is the core source of quality data — every row
carries a score, a tasting-text, and the Munskänkarna session it was
published in.

### Request shape

- POST-only; GET returns HTTP 404 `[M021]`.
- Accepts `application/x-www-form-urlencoded` or a JSON body;
  both produce the same response shape `[M022]`.
- No auth; a minimal empty POST succeeds with HTTP 200 `[M020]`.

| Parameter                     | Role                                                                      |
|-------------------------------|---------------------------------------------------------------------------|
| `pageIndex`                   | **Silently ignored** — see pagination notes below                         |
| `pageSize`                    | Caps the number of rows returned                                          |
| `sortOrder`                   | Must be empty string; any other value returns HTTP 500                    |
| `wineBottleActivityName[]`    | Repeatable; filters to the union of the named sessions                    |

### Response shape

- The response is a JSON object with top-level keys `result` (array of
  rows), `total` (integer), and `facets` (object) `[M023]`.
- Every row in `result` exposes this full field set — the same set
  consumed by `scrape_wines.flatten()` `[M024]`:
  `wineBottleName`, `wineBottleYearName`, `wineBottleCategoryName`,
  `wineBottleCountryName`, `wineBottleCountryAlias`,
  `wineBottleRegionName`, `wineBottleSubRegionName`,
  `wineBottleProducerName`, `wineBottleImporter`, `wineBottlePrice`,
  `wineBottleVolume`, `wineBottleAlcohol`, `wineBottleSugarContent`,
  `wineBottleRatePoints`, `wineBottleRateText`,
  `wineBottleRateIsTypical`, `wineBottleRateCanBeStored`,
  `wineBottleRateCategorySymbol`, `wineBottleRawMaterials`,
  `wineBottleActivityName`, `wineBottleActivityPublishDate`,
  `wineBottleActivityUrl`, `wineBottleUrl`, `wineBottleExternalLink`.

### Field types (easy to get wrong)

- `wineBottlePrice`, `wineBottleVolume`, `wineBottleAlcohol`,
  `wineBottleSugarContent`, and `wineBottleYearName` are all **JSON
  strings**, not numbers — clients must parse them before doing
  arithmetic `[M025]`. `clean_wines.py` exists partly to absorb this.
- `wineBottleRatePoints` is the only numeric scalar: a JSON float in
  0.5-point increments on the Munskänkarna 9–20 scale `[M026]`.

### `wineBottleExternalLink` — the Systembolaget bridge

This field is the only link between a Munskänkarna tasting note and a
Systembolaget product. Handle with care.

- When present, `wineBottleExternalLink` is an object with exactly two
  keys — `text` and `link` — each a string or null `[M027]`.
- `text` is usually a Systembolaget article number. In a full corpus
  snapshot, ≥ 80% of non-empty `text` values are all-digit strings
  (either 4-5-digit legacy article numbers or 6+-digit modern
  `productNumber`s) `[M028]`.
- A significant minority of rows use the sentinel `"Nätvin"` —
  Munskänkarna's marker for online-only wines without a physical SKU.
  Clients must treat `"Nätvin"` (and its typos: `"Nätvine"`,
  `"Nåtvin"`) as "no article number", not parse it as an id `[M029]`.
- Other text values seen in the wild: empty string, missing entirely,
  or occasional data-entry garbage (`"71759-01"`, `"jan-60"`, etc.)
  — downstream code must tolerate these.

### Pagination does not work the way you expect

- `pageIndex` is **silently ignored**. Sending `pageIndex=0`,
  `pageIndex=1`, or `pageIndex=7` with identical other parameters
  returns the same rows (always the first N) `[M030]`. There is no
  true pagination on this endpoint.
- `pageSize` sets the maximum number of rows returned. When
  `pageSize < total`, the response contains exactly `pageSize` rows;
  when `pageSize >= total`, it contains `total` rows `[M031]`.
- There is **no observed upper cap on `pageSize`**: a single request
  with `pageSize=100000` returns the entire unfiltered corpus —
  tens of thousands of rows — in one response `[M032]`. This is the
  only sane way to retrieve everything.

**Practical consequence.** Do not write a pagination loop. Compute or
estimate the required size, set `pageSize` larger than it, and issue
one request. If you must iterate, partition by `wineBottleActivityName[]`
rather than by `pageIndex`.

> **Note on `scrape_wines.py`.** The scraper assumes a
> "wrap-around on the last page" behaviour and paginates within each
> session batch. With today's API, the second page is silently the
> same rows as the first — the scraper is only correct because each
> batch's row count fits inside `pageSize=1000`. If a batch ever
> exceeded that, the truncation logic at `scrape_wines.py:121` would
> silently discard real data. A future rewrite should drop pagination
> entirely.

### Filtering by session

- `wineBottleActivityName[]` is a real filter: every returned row's
  `wineBottleActivityName` matches the filter. Note that the response
  field carries the **label only** (e.g. `"Beställningssortimentet
  1998 01 Januari"`), whereas the filter key has the `YYYYMMDD-`
  prefix (`"19980101-Beställningssortimentet 1998 01 Januari"`). Joins
  between request and response must strip or add the prefix
  accordingly `[M033]`.
- The parameter is repeatable; the server ORs the values. When the
  selected sessions are disjoint, `total` for the combined filter
  equals the sum of the per-session totals `[M034]`.
- Filtering on an unknown session key returns `total=0` and an empty
  `result` — no HTTP error `[M035]`.

### `sortOrder` is a trap

- `sortOrder` must be the empty string. Any non-empty value — even
  plausible-looking ones like `"price"` or `"points"` — returns HTTP
  500 `[M036]`. There is no working server-side sort; clients must
  sort after fetching.

### Unfiltered queries duplicate rows

- Without a `wineBottleActivityName[]` filter, each tasting note is
  returned **once per session it was published to**. The row count
  exceeds the number of distinct `(wineBottleName,
  wineBottleYearName)` pairs `[M037]`. The reported `total` reflects
  the duplicated row count.
- Quantitatively, the duplication rate in the current corpus sits in
  the single-digit-percent range — not the 52× factor older comments
  in `scrape_wines.py` describe. The claim is: duplication exists
  and the unfiltered total is larger than the distinct-wine count;
  the exact ratio is volatile.

**Implication.** If you want a clean, deduplicated dataset, either
dedup on `(wineBottleName, wineBottleYearName, wineBottleProducerName)`
client-side, or — for a stable key — partition by session via
`wineBottleActivityName[]` and dedup across partitions.

---

## Cross-endpoint invariants

These are the guarantees that make it possible to combine data from
`getfacets/` and `listwinebottles/` coherently.

- A session's facet count agrees with its filtered list total: for
  any `facets.wineBottleActivityName[i]`, the parenthesised `item3`
  equals `listwinebottles.total` when filtering by that entry's
  `item2` key `[M040]`.
- **The sum of all `wineBottleActivityName` facet counts equals the
  unfiltered `listwinebottles.total`** `[M041]`. This confirms that
  the unfiltered list is the disjoint union of per-session lists —
  each row appears once per session it was published to — and
  quantifies the "duplication across sessions" effect above.
- Every `wineBottleActivityName[*].item2` round-trips as a valid
  `wineBottleActivityName[]` filter — the two endpoints share a
  session-key namespace `[M042]`.

---

## Claim index

| ID   | Claim                                                                                                  | Test |
|------|--------------------------------------------------------------------------------------------------------|------|
| M001 | getfacets returns 200 with a JSON body                                                                  | `api-docs/munskankarna/tests/test_getfacets.py::test_M001_getfacets_endpoint_returns_200` |
| M002 | getfacets is GET-only (POST returns 404)                                                                | `api-docs/munskankarna/tests/test_getfacets.py::test_M002_getfacets_is_get_only` |
| M003 | getfacets body has a single top-level `facets` object                                                   | `api-docs/munskankarna/tests/test_getfacets.py::test_M003_getfacets_response_has_top_level_facets_object` |
| M004 | getfacets exposes the documented facet categories                                                       | `api-docs/munskankarna/tests/test_getfacets.py::test_M004_getfacets_exposes_expected_facet_categories` |
| M005 | Facet entries are `{item1,item2,item3,item4}` tuples                                                    | `api-docs/munskankarna/tests/test_getfacets.py::test_M005_facet_entries_use_item1_item4_tuple_shape` |
| M006 | Session keys have the form `YYYYMMDD-<label>`                                                           | `api-docs/munskankarna/tests/test_getfacets.py::test_M006_activity_name_facet_exposes_session_keys` |
| M007 | The session archive spans hundreds of entries                                                           | `api-docs/munskankarna/tests/test_getfacets.py::test_M007_activity_name_facet_includes_hundreds_of_sessions` |
| M008 | activityType enumerates standard assortment buckets                                                     | `api-docs/munskankarna/tests/test_getfacets.py::test_M008_activity_type_facet_exposes_assortment_buckets` |
| M020 | listwinebottles POST returns 200 with JSON                                                              | `api-docs/munskankarna/tests/test_listwinebottles.py::test_M020_listwinebottles_endpoint_returns_200_for_minimal_post` |
| M021 | listwinebottles is POST-only (GET returns 404)                                                          | `api-docs/munskankarna/tests/test_listwinebottles.py::test_M021_listwinebottles_is_post_only` |
| M022 | Accepts both form-urlencoded and JSON bodies                                                            | `api-docs/munskankarna/tests/test_listwinebottles.py::test_M022_listwinebottles_accepts_json_body` |
| M023 | Response has `result` (array), `total` (int), `facets` (object)                                         | `api-docs/munskankarna/tests/test_listwinebottles.py::test_M023_listwinebottles_response_has_result_total_facets` |
| M024 | Each row carries the documented field set                                                               | `api-docs/munskankarna/tests/test_listwinebottles.py::test_M024_listwinebottles_rows_expose_documented_fields` |
| M025 | Price/volume/alcohol/sugar/year are JSON strings                                                        | `api-docs/munskankarna/tests/test_listwinebottles.py::test_M025_numeric_fields_are_json_strings` |
| M026 | `wineBottleRatePoints` is a JSON number                                                                 | `api-docs/munskankarna/tests/test_listwinebottles.py::test_M026_rating_points_is_a_float` |
| M027 | `wineBottleExternalLink` is `{text, link}` when present                                                 | `api-docs/munskankarna/tests/test_listwinebottles.py::test_M027_external_link_shape` |
| M028 | Most external-link texts are digit-string article numbers                                               | `api-docs/munskankarna/tests/test_listwinebottles.py::test_M028_external_link_text_is_usually_a_systembolaget_article_number` |
| M029 | `Nätvin` sentinel appears as the link text for online-only wines                                        | `api-docs/munskankarna/tests/test_listwinebottles.py::test_M029_external_link_text_includes_natvin_marker` |
| M030 | `pageIndex` is silently ignored                                                                         | `api-docs/munskankarna/tests/test_listwinebottles.py::test_M030_pageIndex_is_silently_ignored` |
| M031 | `pageSize` caps `len(result)` to `min(pageSize, total)`                                                 | `api-docs/munskankarna/tests/test_listwinebottles.py::test_M031_pageSize_caps_result_length` |
| M032 | `pageSize` has no observed upper cap                                                                    | `api-docs/munskankarna/tests/test_listwinebottles.py::test_M032_pageSize_has_no_observed_upper_cap` |
| M033 | `wineBottleActivityName[]` is a real filter; response label drops the `YYYYMMDD-` prefix                | `api-docs/munskankarna/tests/test_listwinebottles.py::test_M033_activity_name_filter_restricts_results` |
| M034 | `wineBottleActivityName[]` is repeatable; the server ORs values                                         | `api-docs/munskankarna/tests/test_listwinebottles.py::test_M034_activity_name_filter_is_repeatable_and_ORs_values` |
| M035 | Unknown session key → `total=0`, empty `result`, no HTTP error                                          | `api-docs/munskankarna/tests/test_listwinebottles.py::test_M035_unknown_session_key_returns_empty_result` |
| M036 | Non-empty `sortOrder` returns HTTP 500                                                                  | `api-docs/munskankarna/tests/test_listwinebottles.py::test_M036_non_empty_sortOrder_returns_500` |
| M037 | Unfiltered queries duplicate each wine once per session it was published to                             | `api-docs/munskankarna/tests/test_listwinebottles.py::test_M037_unfiltered_query_duplicates_wines_across_sessions` |
| M040 | Activity facet count equals filtered `listwinebottles.total`                                            | `api-docs/munskankarna/tests/test_cross_endpoint.py::test_M040_activity_facet_count_matches_listwinebottles_total` |
| M041 | Sum of activity facet counts equals unfiltered total                                                    | `api-docs/munskankarna/tests/test_cross_endpoint.py::test_M041_sum_of_activity_facet_counts_equals_unfiltered_total` |
| M042 | Activity `item2` round-trips as a `wineBottleActivityName[]` filter                                     | `api-docs/munskankarna/tests/test_cross_endpoint.py::test_M042_activity_facet_item2_is_accepted_by_list_filter` |
