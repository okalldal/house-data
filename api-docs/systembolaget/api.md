# Systembolaget API — Verified Reference

Every claim on this page is backed by at least one probe in
`api-docs/systembolaget/tests/`. Claim tags like `[C001]` map to test
functions named `test_C001_...`. See `STRATEGY.md` (alongside this file)
for the research approach, and run
`pytest api-docs/systembolaget/tests/` from the repo root to re-verify
the whole document against the live API.

- **Base URL:** `https://api-extern.systembolaget.se`
- **Auth:** the key is a public frontend token visible in browser DevTools;
  see `api-docs/systembolaget/tests/conftest.py` for the current value.

---

## Request headers

All probes send:

```
Ocp-Apim-Subscription-Key: <key>
Origin:                    https://www.systembolaget.se
Accept:                    application/json
```

The `Ocp-Apim-Subscription-Key` header is required. Both the catalog
endpoint `[C003]` and the search endpoint `[C037]` reject requests without
it with HTTP 401.

---

## Catalog — `GET /sb-api-ecommerce/v1/product`

The catalog is a **sparse index of all products** (not only wine). It is a
single JSON response, ~7 MB on the wire.

- Returns HTTP 200 with the standard headers `[C001]`.
- Body is a JSON array at the top level `[C002]`.
- Each item has exactly these eight keys `[C007]`:
  `productNumber`, `productId`, `categoryLevel1`, `productNameBold`,
  `imageUrl`, `isHidden`, `isSearchable`, `lastModified`.
- `productNumber` and `productId` are both JSON strings `[C008]`.
- `productNumber` is unique within the catalog — one item per SKU `[C009]`.
- `categoryLevel1` partitions products by kind; the value set includes
  at least `"Vin"` and `"Sprit"` `[C005]`.
- `categoryLevel1` can be `null`; callers must handle the None case rather
  than assume every item is categorised `[C010]`.
- **No vintage field.** Catalog items classified as `"Vin"` do not carry
  vintage information — vintage is only available via the search endpoint
  `[C006]`.

**Implication.** The catalog is useful for `productNumber → productId`
lookup, category filtering, and enumeration of SKU identity. For anything
else (price, stock, vintage, name, country, etc.) you must query the
search or stock endpoints.

### productNumber sibling groups

The last two characters of a wine `productNumber` encode a packaging /
size variant. Many wines appear as a **sibling group** — multiple
productNumbers sharing the first N-2 characters, differing only in
the final two (typically `01`, `02`, `06`, `08`, …). The catalog
consistently exposes tens to hundreds of such groups `[C011]`.

Within a sibling group, **most** (≥ 80% observed) groups share a single
`productNameBold` — i.e. they really are the same wine packaged
differently `[C012]`. The remaining ~20% is a mix of:

- **Data-quality noise** (the dominant case). The two entries are the
  same wine / same producer but `productNameBold` is populated
  inconsistently — e.g. cuvée name on one row and producer name on
  the other (`71832` → `"Côtes du Rhône Saint-Esprit"` vs
  `"Delas Frères"`), a subregion suffix dropped on one row
  (`"Amarone della Valpolicella"` vs `"Amarone della Valpolicella
  Classico"`), a typo (`"Beaumont des Crayères"` vs `"Beaumont de
  Crayères"`), or producer-name spelling drift
  (`"Gancia"` vs `"F.LLI GANCIA & C SpA"`).
- **Genuine prefix collisions** (a small minority). Unrelated products
  share a prefix — typically because a retired SKU's prefix was later
  reused, occasionally just by coincidence within one producer's
  range.

**This is not a hard rule.** Prefix-sharing is a same-wine *heuristic*,
accurate most of the time but wrong a small, real fraction of the time,
and there is no clean server-side signal that separates the two cases.
If you need canonical identity — for pricing, ranking, or merging with
external data — confirm with a second signal (producer match + name
similarity, or explicit user disambiguation). Do not treat the prefix
relationship alone as an identity key.

Packaging variation within a sibling group is verified on the search
endpoint — see the packaging section below.

---

## Product search — `GET /sb-api-ecommerce/v1/productsearch/search`

The search endpoint is the richest source of product data — each result
carries price, vintage, country, grapes, taste profile, assortment
classification, and more.

### Response shape

- Returns HTTP 200 for a minimal `{categoryLevel1=Vin, page=1}` query `[C020]`.
- Response is a JSON object with top-level keys `products`, `metadata`,
  `filters` `[C021]`.
- A page returns up to 30 products (the default page size) `[C022]`.
- Each product exposes `productId` and `productNumber` — the same keys the
  catalog uses `[C024]`, with `productId` encoded as a string `[C033]` so
  the join is direct.
- Each product exposes a `vintage` field — either a year string or null
  for non-vintage wines `[C023]`, `[C034]`.

### `metadata` and `filters`

- `metadata` contains integer `docCount`, integer `totalPages`, and an
  object `priceRange` with numeric `min` and `max` `[C025]`.
- `filters` is an array; each entry has `name` (string) and
  `searchModifiers` (array) `[C026]`.
- Every entry in `searchModifiers` exposes a `value` field — the token a
  caller feeds back as the matching query parameter `[C027]`.
- The filter set includes `Country`, `Vintage`, and `AssortmentText`
  among others `[C028]`.

### Query parameters

- `country` restricts results: every returned product has a matching
  `country` value `[C031]`.
- `Vintage` restricts results: every returned product has a matching
  `vintage` string `[C032]`.
- `storeId` is **silently ignored**: supplying any value (valid, invalid,
  or absent) does not change `docCount` `[C029]`.
- `siteId` is **silently ignored** in the same way `[C030]`.
- `AssortmentText` is a real filter that narrows to a single sourcing
  category (e.g. `Ordervaror`); the matching products carry that same
  `assortmentText` value in their own record `[C039]`.

### AssortmentText values

The `AssortmentText` filter's `searchModifiers` include at least the
values `Fast sortiment` (permanent range), `Tillfälligt sortiment`
(temporary), and `Ordervaror` (advance-order only) `[C038]`. These are
the tokens to pass back as the `AssortmentText` query parameter.

### The Elasticsearch 10,000-result cap

Generic wine pagination is capped well below the real page count:
`metadata.totalPages` for `{categoryLevel1=Vin}` is strictly less than
`ceil(docCount / 30)` `[C035]`. Quantitatively, `totalPages * pageSize`
is bounded at ~10,000 — a dead ringer for the Elasticsearch
`max_result_window` default `[C052]`.

Partitioning by `country` works around the cap — each country's
`totalPages` covers its full `docCount` `[C036]`, and every country
partition observed is comfortably under the window. This is why bulk
scraping must paginate per country rather than sequentially through the
unfiltered result set.

### Country-partition pagination is not deduplicated

Iterating all pages of a single-country wine search returns exactly
`metadata.docCount` result rows `[C054]`. These rows are **not
deduplicated server-side**: a few percent of productNumbers (0–6%
observed across sample countries) appear on more than one page,
presumably due to ES index shifts mid-scroll. Clients that want a
unique-product set must dedup locally — do not assume row count equals
unique count.

### The `q` parameter is silently ignored

Despite its appearance in third-party documentation as a free-text
search, the `q` query parameter is silently ignored: `docCount` and the
first-page product ids are identical for `q` absent, empty, a real wine
term, or random garbage `[C053]`. Free-text search must be implemented
client-side (e.g. by paginating a country partition and filtering by
`productNameBold` in Python) — there is no server-side text search on
this endpoint.

---

## All-store stock — `GET /sb-api-ecommerce/v1/site/stores/{productId}/`

One call returns current stock for a single product at **every**
Systembolaget store.

- Returns HTTP 200 for a valid `productId` `[C040]`.
- Response has `totalNumberOfStores` (int) and `storeStocks` (array) at
  the top level `[C041]`.
- `totalNumberOfStores` equals `len(storeStocks)` — it's the count of
  entries in the response, not a catalog-wide total `[C045]`.
- In practice the response contains several hundred entries — the full
  store network `[C046]`.
- Each entry pairs a `store` record with a `stockBalance` record `[C042]`.
- `store` carries at minimum `siteId`, `alias`, `address`, `city`, `county`,
  `postalCode` `[C043]`.
- `stockBalance` exposes integer `stock`, string `productId`, string
  `storeId`, and `shelf` which is **either a string or null** — null has
  been observed even when `stock > 0` `[C044]`.
- Within an entry, `stockBalance.storeId == store.siteId` — the two
  sub-objects share a site id `[C047]`.

### Store-record operational flags

Each `store` record exposes a set of booleans and a `depotStockId`:
`isActive`, `isOpen`, `isBlocked`, `isDepot`, `isStore`, `isTastingStore`,
`isFullAssortmentOrderStore`, and `depotStockId` (string) `[C048]`.

Two of these are uninformative across a full response:

- `isStore` is **always `false`** despite the name — it does not
  indicate store-ness. Do not filter on it `[C049]`.
- `isDepot` is **always `false`** — this endpoint returns only stores.
  Depot-level inventory lives behind the separate
  `/stockbalance/depot/{depotId}/{productId}` endpoint `[C050]`.

`depotStockId` points each store at its supplying depot. The number of
distinct depots is tiny relative to the number of stores — Sweden is
served by a handful of central warehouses, not one per store `[C051]`.

Bandwidth is ~650 KB per call. Use this endpoint when you want availability
across many stores for one product. Use the single-store endpoint below
when you want availability for one (store, product) pair.

---

## Packaging / size variants (sibling groups)

Within a wine sibling group (productNumbers sharing the first N-2
characters — see C011/C012 in the catalog section), the search endpoint
exposes the **differentiating attributes** that the catalog hides.

- At least some sibling groups contain members with different `volume`
  values — the last two productNumber characters can encode **bottle
  size** (e.g. `772001` @ 750 ml, `772002` @ 375 ml) `[C013]`.
- At least some sibling groups contain members with different
  `packagingLevel1` values — the suffix can also encode **packaging
  type** (glass bottle vs bag-in-box vs can, etc.) `[C014]`.
- Sibling groups observed via search usually share `productNameBold`
  (≥ 80%), consistent with the catalog's view `[C015]`. The
  not-always part has the same character as in the catalog —
  mostly inconsistent name population, occasionally a real prefix
  collision; see the sibling-group section above.

**Practical consequence.** If an application wants "the 750 ml version"
of a wine, it must select a specific sibling by consulting `volume` (and
`packagingLevel1`) on each member. Do not treat sibling members as
interchangeable: price, volume, and packaging vary.

---

## Single-store stock — `GET /sb-api-ecommerce/v1/stockbalance/store/{siteId}/{productId}`

Real-time stock for one product at one store; ~1 KB response.

- Returns HTTP 200 for a valid `(siteId, productId)` pair `[C060]`.
- Response has `stock`, `isInStoreAssortment`, `shelf` `[C061]`.
- `stock` is an integer; `isInStoreAssortment` is a boolean `[C062]`.
- `shelf` is a string or null (null observed even with `stock > 0`) `[C063]`.
- Values agree with the corresponding entry in the all-store response —
  both endpoints read from the same underlying inventory data `[C064]`.

**`isInStoreAssortment` does not imply stock.** Products classified as
`Ordervaror` have `isInStoreAssortment=false` on every store, yet can
still have `stock > 0` at individual stores that keep physical copies for
advance-order pickups. The two signals are independent `[C065]` — do
not treat `isInStoreAssortment=false` as "out of stock".

---

## Depot stock — `GET /sb-api-ecommerce/v1/stockbalance/depot/{depotId}/{productId}`

Central-warehouse inventory for one product at one depot — what the
systembolaget.se frontend uses to show home-delivery availability.

- Returns HTTP 200 when called with a `depotId` taken from a store's
  `depotStockId` in the all-store response `[C100]`.
- Response is a tiny JSON object with exactly the keys `productId`,
  `depotId`, `stock` (integer). No shelf or assortment data `[C101]`.
- `productId` and `depotId` in the body echo the URL path parameters
  `[C102]`.

To enumerate depots, call the all-store endpoint and take the distinct
set of `store.depotStockId` values (only a few exist system-wide).

---

## Postcode → home delivery — `GET /sb-api-ecommerce/v1/postalCode/{code}`

Maps a Swedish 5-digit postcode to the depot that serves home deliveries
there. This is the missing bridge between a customer's address and the
depot-level stock endpoint: given a postcode, look up the `depotStockId`,
then query `/v1/stockbalance/depot/{depotStockId}/{productId}` to see
whether a given wine is actually orderable for delivery.

- Returns HTTP 200 for a valid, assigned 5-digit postcode `[C120]`.
- Response body carries `postalCode`, `postalCity`, `homeOrderApplicable`
  (bool), and `depotStockId` (numeric string) `[C121]`. Additional fields
  (`isSustainableDelivery`, `firstAvailableHomeDeliveryDate`,
  `deliveryDates`) are delivery-scheduling metadata not load-bearing for
  inventory questions.
- Both compact (`11454`) and space-separated (`114 54`) forms resolve to
  the same record `[C122]`.
- Unassigned 5-digit codes return HTTP 404 with an "Entity ... was not
  found" body — distinct from the 200-with-null-fields pattern `[C123]`.
- Wrong-length codes return HTTP 400 with a validation message naming
  `PostalCode` `[C124]`.
- `depotStockId` is drawn from the same identifier space as
  `store.depotStockId` on the all-store endpoint `[C125]`.
- The same value works unchanged as `depotId` on
  `/v1/stockbalance/depot/{depotId}/{productId}` `[C126]`.
- Different regions map to different depots — depot routing is
  geographic, not a single national warehouse `[C127]`.

**Practical consequence.** To answer "is wine X orderable to postcode
11454?", first resolve the postcode to its `depotStockId` via this
endpoint, then query the depot stock endpoint for that (depot, product)
pair. A `homeOrderApplicable=false` response short-circuits the lookup —
the postcode is not served by home delivery at all.

---

## Store lookup — `GET /sb-api-ecommerce/v1/sitesearch/site`

Find stores by name, city, or proximity.

- Returns HTTP 200 `[C070]`.
- Response has a `siteSearchResults` array `[C071]`.
- Each result exposes `siteId`, `displayName`, `city`, `isAgent` `[C072]`.
- `siteId` is a zero-padded 4-digit numeric **string** (e.g. `"0102"`, not
  the integer `102`) for non-agent stores `[C076]`.
- Results mix two kinds: Systembolaget's own stores (`isAgent=false`) and
  third-party alcohol-agents/ombuds (`isAgent=true`). Callers must filter
  by `isAgent` when they want only real stores `[C073]`.
- An empty `q` returns the entire store network in one call `[C074]`.
- `q` performs a **geographic / proximity** match, not a literal substring
  match — searching for a place name can return stores in neighbouring
  municipalities whose `displayName` and `city` don't contain the query at
  all `[C075]`.

---

## Cross-endpoint / interop

These are the invariants that make it possible to combine data across
endpoints.

- `productId` joins the catalog and search endpoints: a search product's
  `productNumber` resolves to a catalog item with the same `productId`
  `[C080]`.
- Every `productNumber` the search endpoint returns also exists in the
  catalog — search does not include SKUs the catalog omits `[C081]`.
- The catalog is **larger** than the wine search result set because it
  spans all product kinds, not just wine `[C082]`.
- The all-store stock endpoint never returns stock for a different
  product — every `stockBalance.productId` equals the productId in the URL
  `[C083]`.

---

## Claim index

| ID   | Claim                                                                                                  | Test |
|------|--------------------------------------------------------------------------------------------------------|------|
| C001 | Catalog endpoint returns HTTP 200 with standard headers                                                | `api-docs/systembolaget/tests/test_catalog.py::test_C001_catalog_endpoint_returns_200` |
| C002 | Catalog response body is a top-level JSON array                                                        | `api-docs/systembolaget/tests/test_catalog.py::test_C002_catalog_response_is_json_array` |
| C003 | Missing subscription key on catalog → HTTP 401                                                         | `api-docs/systembolaget/tests/test_catalog.py::test_C003_missing_subscription_key_returns_401` |
| C004 | Catalog items carry productNumber, productId, categoryLevel1                                           | `api-docs/systembolaget/tests/test_catalog.py::test_C004_catalog_items_have_core_identity_fields` |
| C005 | categoryLevel1 value set includes "Vin" and "Sprit"                                                    | `api-docs/systembolaget/tests/test_catalog.py::test_C005_catalog_categoryLevel1_partitions_product_kinds` |
| C006 | Catalog wine items carry no vintage field                                                              | `api-docs/systembolaget/tests/test_catalog.py::test_C006_catalog_wine_items_have_no_vintage_field` |
| C007 | Catalog is a sparse index: exactly 8 keys per item                                                     | `api-docs/systembolaget/tests/test_catalog.py::test_C007_catalog_is_a_sparse_index` |
| C008 | productNumber and productId are JSON strings                                                           | `api-docs/systembolaget/tests/test_catalog.py::test_C008_catalog_identity_fields_are_json_strings` |
| C009 | productNumber is unique within the catalog                                                             | `api-docs/systembolaget/tests/test_catalog.py::test_C009_catalog_productNumber_is_unique` |
| C010 | categoryLevel1 can be null                                                                             | `api-docs/systembolaget/tests/test_catalog.py::test_C010_catalog_categoryLevel1_can_be_null` |
| C011 | Wine productNumbers form sibling groups via shared first N-2 chars                                     | `api-docs/systembolaget/tests/test_catalog.py::test_C011_wine_productNumbers_form_sibling_groups` |
| C012 | Siblings usually (≥80%) but not always share productNameBold                                           | `api-docs/systembolaget/tests/test_catalog.py::test_C012_siblings_usually_but_not_always_share_productNameBold` |
| C013 | Siblings can differ in volume (last 2 digits can encode bottle size)                                   | `api-docs/systembolaget/tests/test_packaging.py::test_C013_siblings_can_differ_in_volume` |
| C014 | Siblings can differ in packagingLevel1 (suffix can encode packaging type)                              | `api-docs/systembolaget/tests/test_packaging.py::test_C014_siblings_can_differ_in_packagingLevel1` |
| C015 | In the search sample, siblings usually share productNameBold                                           | `api-docs/systembolaget/tests/test_packaging.py::test_C015_siblings_usually_share_productName_in_search` |
| C020 | Search endpoint returns HTTP 200 for a minimal query                                                   | `api-docs/systembolaget/tests/test_search.py::test_C020_search_endpoint_returns_200` |
| C021 | Search response has top-level products/metadata/filters                                                | `api-docs/systembolaget/tests/test_search.py::test_C021_search_response_has_products_metadata_filters` |
| C022 | Default page size is 30                                                                                | `api-docs/systembolaget/tests/test_search.py::test_C022_search_default_page_size_is_30` |
| C023 | Search products expose a vintage field                                                                 | `api-docs/systembolaget/tests/test_search.py::test_C023_search_products_expose_vintage_field` |
| C024 | Search products expose productId and productNumber                                                     | `api-docs/systembolaget/tests/test_search.py::test_C024_search_products_expose_core_identity_fields` |
| C025 | Metadata has docCount, totalPages, priceRange{min,max}                                                 | `api-docs/systembolaget/tests/test_search.py::test_C025_search_metadata_has_docCount_totalPages_priceRange` |
| C026 | Filters array; each filter has name + searchModifiers                                                  | `api-docs/systembolaget/tests/test_search.py::test_C026_search_filters_is_array_of_named_filters` |
| C027 | Each searchModifier exposes a value field                                                              | `api-docs/systembolaget/tests/test_search.py::test_C027_search_modifier_exposes_value` |
| C028 | Filter set includes Country, Vintage, AssortmentText                                                   | `api-docs/systembolaget/tests/test_search.py::test_C028_search_filters_include_country_vintage_assortment` |
| C029 | storeId parameter is silently ignored                                                                  | `api-docs/systembolaget/tests/test_search.py::test_C029_search_storeId_param_is_silently_ignored` |
| C030 | siteId parameter is silently ignored                                                                   | `api-docs/systembolaget/tests/test_search.py::test_C030_search_siteId_param_is_silently_ignored` |
| C031 | country parameter is a real filter                                                                     | `api-docs/systembolaget/tests/test_search.py::test_C031_search_country_param_restricts_results` |
| C032 | Vintage parameter is a real filter                                                                     | `api-docs/systembolaget/tests/test_search.py::test_C032_search_Vintage_param_restricts_by_year` |
| C033 | Search productId is a JSON string                                                                      | `api-docs/systembolaget/tests/test_search.py::test_C033_search_productId_is_string` |
| C034 | Some products have vintage=null (non-vintage wines)                                                    | `api-docs/systembolaget/tests/test_search.py::test_C034_search_exposes_null_vintage_for_non_vintage_wines` |
| C035 | totalPages is capped below the real page count (ES window)                                             | `api-docs/systembolaget/tests/test_search.py::test_C035_search_totalPages_is_capped_below_real_page_count` |
| C036 | Country partition fits within the cap                                                                  | `api-docs/systembolaget/tests/test_search.py::test_C036_search_country_partition_fits_within_cap` |
| C037 | Missing subscription key on search → HTTP 401                                                          | `api-docs/systembolaget/tests/test_search.py::test_C037_search_no_api_key_returns_401` |
| C038 | AssortmentText filter values include Fast/Tillfälligt/Ordervaror                                       | `api-docs/systembolaget/tests/test_search.py::test_C038_AssortmentText_filter_enumerates_standard_categories` |
| C039 | AssortmentText parameter is a real filter                                                              | `api-docs/systembolaget/tests/test_search.py::test_C039_search_AssortmentText_param_filters_results` |
| C052 | totalPages*30 capped at ~10,000 (ES max_result_window)                                                 | `api-docs/systembolaget/tests/test_search.py::test_C052_search_totalPages_caps_at_the_10000_result_window` |
| C053 | `q` query parameter is silently ignored                                                                | `api-docs/systembolaget/tests/test_search.py::test_C053_search_q_parameter_is_silently_ignored` |
| C054 | Country-partition row count equals docCount; rows are NOT deduplicated server-side                    | `api-docs/systembolaget/tests/test_search.py::test_C054_country_partition_row_count_equals_docCount` |
| C040 | All-store endpoint returns 200 for a valid productId                                                   | `api-docs/systembolaget/tests/test_all_store_stock.py::test_C040_all_store_endpoint_returns_200` |
| C041 | All-store response has totalNumberOfStores + storeStocks                                               | `api-docs/systembolaget/tests/test_all_store_stock.py::test_C041_all_store_response_has_totalNumberOfStores_and_storeStocks` |
| C042 | storeStocks entries pair `store` and `stockBalance`                                                    | `api-docs/systembolaget/tests/test_all_store_stock.py::test_C042_all_store_stocks_pair_store_and_stockBalance` |
| C043 | store object has siteId/alias/address/city/county/postalCode                                           | `api-docs/systembolaget/tests/test_all_store_stock.py::test_C043_all_store_store_object_has_identity_fields` |
| C044 | stockBalance: int stock, str productId/storeId, shelf is str or null                                   | `api-docs/systembolaget/tests/test_all_store_stock.py::test_C044_all_store_stockBalance_has_core_fields` |
| C045 | totalNumberOfStores == len(storeStocks)                                                                | `api-docs/systembolaget/tests/test_all_store_stock.py::test_C045_all_store_totalNumberOfStores_matches_list_length` |
| C046 | All-store returns several hundred entries (full store network)                                         | `api-docs/systembolaget/tests/test_all_store_stock.py::test_C046_all_store_returns_hundreds_of_stores` |
| C047 | stockBalance.storeId == store.siteId                                                                   | `api-docs/systembolaget/tests/test_all_store_stock.py::test_C047_all_store_stock_join_keys_are_consistent` |
| C048 | Store record exposes operational flags + depotStockId                                                  | `api-docs/systembolaget/tests/test_all_store_stock.py::test_C048_all_store_records_carry_operational_flags` |
| C049 | isStore is always false (uninformative)                                                                | `api-docs/systembolaget/tests/test_all_store_stock.py::test_C049_all_store_isStore_is_always_false` |
| C050 | isDepot is always false on this endpoint                                                               | `api-docs/systembolaget/tests/test_all_store_stock.py::test_C050_all_store_isDepot_is_always_false` |
| C051 | Many stores share a small number of depots                                                             | `api-docs/systembolaget/tests/test_all_store_stock.py::test_C051_all_store_depotStockId_maps_many_stores_to_few_depots` |
| C060 | Single-store endpoint returns 200 for a valid pair                                                     | `api-docs/systembolaget/tests/test_single_store_stock.py::test_C060_single_store_endpoint_returns_200` |
| C061 | Single-store response exposes stock, isInStoreAssortment, shelf                                        | `api-docs/systembolaget/tests/test_single_store_stock.py::test_C061_single_store_response_has_stock_assortment_shelf` |
| C062 | Single-store: stock is int, isInStoreAssortment is bool                                                | `api-docs/systembolaget/tests/test_single_store_stock.py::test_C062_single_store_stock_is_int_and_assortment_is_bool` |
| C063 | Single-store: shelf is string or null                                                                  | `api-docs/systembolaget/tests/test_single_store_stock.py::test_C063_single_store_shelf_is_string_or_null` |
| C064 | Single-store stock agrees with all-store endpoint                                                      | `api-docs/systembolaget/tests/test_single_store_stock.py::test_C064_single_store_agrees_with_all_store_endpoint` |
| C065 | Ordervaror products can have store stock despite isInStoreAssortment=false                             | `api-docs/systembolaget/tests/test_single_store_stock.py::test_C065_ordervaror_can_have_store_stock_despite_not_in_assortment` |
| C070 | Sitesearch returns 200                                                                                 | `api-docs/systembolaget/tests/test_sitesearch.py::test_C070_sitesearch_endpoint_returns_200` |
| C071 | Response has siteSearchResults array                                                                   | `api-docs/systembolaget/tests/test_sitesearch.py::test_C071_sitesearch_response_has_siteSearchResults_array` |
| C072 | Results expose siteId, displayName, city, isAgent                                                      | `api-docs/systembolaget/tests/test_sitesearch.py::test_C072_sitesearch_results_have_core_identity_fields` |
| C073 | isAgent distinguishes real stores from third-party agents                                              | `api-docs/systembolaget/tests/test_sitesearch.py::test_C073_sitesearch_isAgent_distinguishes_real_stores_from_agents` |
| C074 | Empty q returns many stores (full network)                                                             | `api-docs/systembolaget/tests/test_sitesearch.py::test_C074_sitesearch_empty_q_returns_many_stores` |
| C075 | q is geographic / proximity, not substring                                                             | `api-docs/systembolaget/tests/test_sitesearch.py::test_C075_sitesearch_q_is_geographic_not_substring` |
| C076 | siteId is a zero-padded 4-digit string                                                                 | `api-docs/systembolaget/tests/test_sitesearch.py::test_C076_sitesearch_siteId_is_zero_padded_string` |
| C080 | productId joins catalog and search by productNumber                                                    | `api-docs/systembolaget/tests/test_cross_endpoint.py::test_C080_productId_joins_catalog_and_search` |
| C081 | Search productNumber ⊆ catalog productNumber                                                           | `api-docs/systembolaget/tests/test_cross_endpoint.py::test_C081_search_productNumber_always_exists_in_catalog` |
| C082 | Catalog is larger than wine search docCount                                                            | `api-docs/systembolaget/tests/test_cross_endpoint.py::test_C082_catalog_wider_than_search_for_wine` |
| C083 | All-store endpoint never leaks stock for another product                                               | `api-docs/systembolaget/tests/test_cross_endpoint.py::test_C083_all_store_productId_matches_requested` |
| C100 | Depot endpoint returns 200 for a valid (depot, product) pair                                           | `api-docs/systembolaget/tests/test_depot_stock.py::test_C100_depot_endpoint_returns_200` |
| C101 | Depot response has exactly {productId, depotId, stock}                                                 | `api-docs/systembolaget/tests/test_depot_stock.py::test_C101_depot_response_shape` |
| C102 | Depot response echoes URL productId and depotId                                                        | `api-docs/systembolaget/tests/test_depot_stock.py::test_C102_depot_echoes_url_parameters` |
| C110 | `product/{pid}/recommended` requires JWT (401 "JWT not present.")                                      | `api-docs/systembolaget/tests/test_auth_endpoints.py::test_C110_taste_match_requires_jwt` |
| C111 | `productfeedback/` requires JWT                                                                        | `api-docs/systembolaget/tests/test_auth_endpoints.py::test_C111_productfeedback_requires_jwt` |
| C112 | `productnotification/list/` requires JWT                                                               | `api-docs/systembolaget/tests/test_auth_endpoints.py::test_C112_productnotification_list_requires_jwt` |
| C113 | Legacy `productrecommendations/getrecommendations/{id}` returns 404                                    | `api-docs/systembolaget/tests/test_auth_endpoints.py::test_C113_legacy_recommendations_path_does_not_exist` |
| C114 | `beveragelist/` returns 404 (not 401) without JWT                                                      | `api-docs/systembolaget/tests/test_auth_endpoints.py::test_C114_beveragelist_returns_404_without_jwt` |
| C115 | 401 bodies distinguish missing-key (empty) from missing-JWT (structured)                               | `api-docs/systembolaget/tests/test_auth_endpoints.py::test_C115_401_with_key_carries_JWT_not_present_message` |
| C120 | postalCode endpoint returns 200 for a valid assigned postcode                                          | `api-docs/systembolaget/tests/test_postalcode.py::test_C120_postalCode_endpoint_returns_200_for_valid_code` |
| C121 | postalCode body carries postalCode/postalCity/homeOrderApplicable/depotStockId                         | `api-docs/systembolaget/tests/test_postalcode.py::test_C121_postalCode_response_has_delivery_fields` |
| C122 | postalCode accepts both compact and space-separated forms                                              | `api-docs/systembolaget/tests/test_postalcode.py::test_C122_postalCode_supports_space_separated_form` |
| C123 | Unassigned 5-digit codes return HTTP 404                                                               | `api-docs/systembolaget/tests/test_postalcode.py::test_C123_postalCode_404_for_unassigned_code` |
| C124 | Wrong-length postcodes return HTTP 400                                                                 | `api-docs/systembolaget/tests/test_postalcode.py::test_C124_postalCode_400_for_wrong_length` |
| C125 | postalCode depotStockId is in store.depotStockId identifier space                                      | `api-docs/systembolaget/tests/test_postalcode.py::test_C125_depotStockId_matches_all_store_depots` |
| C126 | postalCode depotStockId is a valid depotId for the depot-stock endpoint                                | `api-docs/systembolaget/tests/test_postalcode.py::test_C126_postalCode_depotStockId_is_valid_depot_stock_id` |
| C127 | Different regions map to different depots (geographic routing)                                         | `api-docs/systembolaget/tests/test_postalcode.py::test_C127_postalCode_different_regions_map_to_different_depots` |

---

## Authenticated endpoints (JWT required)

Several endpoints referenced by the systembolaget.se frontend require a
user-session JWT in addition to the subscription key. With the
subscription key alone — i.e. from an app that does not impersonate a
logged-in user — they return:

| Endpoint                                                  | Without JWT | Claim |
|-----------------------------------------------------------|-------------|-------|
| `GET /v1/product/{productId}/recommended` (taste match)   | **401** `JWT not present.` | `[C110]` |
| `GET /v1/productfeedback/` (user ratings)                 | **401** `JWT not present.` | `[C111]` |
| `GET /v1/productnotification/list/` (watchlist)           | **401** | `[C112]` |
| `GET /v1/beveragelist/` (saved lists)                     | **404** | `[C114]` |

The 401 responses carry a structured body `{statusCode: 401, message:
"JWT not present."}`, which distinguishes them from the subscription-key
401 (no JSON body) `[C115]`.

`beveragelist` returns 404 rather than 401, suggesting the route
requires a path component (e.g. a list id) only obtainable through the
authenticated flow `[C114]`.

### Endpoint that does not exist

`GET /v1/productrecommendations/getrecommendations/{productId}` returns
HTTP 404 `[C113]`. The legacy field notes named this path as the
"related products" source; it either moved or never existed on
`api-extern`. Do not rely on it.
