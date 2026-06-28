"""
Probes for the product search endpoint:
    GET /sb-api-ecommerce/v1/productsearch/search

Each test's first docstring line is the claim it establishes.
"""

import requests

SEARCH_PATH = "/sb-api-ecommerce/v1/productsearch/search"


def _search(session, api_base, **params):
    resp = session.get(f"{api_base}{SEARCH_PATH}", params=params, timeout=30)
    resp.raise_for_status()
    return resp.json()


def test_C020_search_endpoint_returns_200(session, api_base):
    """The search endpoint returns HTTP 200 for a minimal {categoryLevel1=Vin, page=1} query."""
    resp = session.get(
        f"{api_base}{SEARCH_PATH}",
        params={"categoryLevel1": "Vin", "page": 1},
        timeout=30,
    )
    assert resp.status_code == 200


def test_C021_search_response_has_products_metadata_filters(search_wine_page1):
    """A search response is a JSON object whose top-level keys include `products`, `metadata`, and `filters`."""
    assert isinstance(search_wine_page1, dict)
    assert "products" in search_wine_page1
    assert "metadata" in search_wine_page1
    assert "filters" in search_wine_page1


def test_C022_search_default_page_size_is_30(search_wine_page1):
    """A single search page returns at most 30 product records (the default page size)."""
    products = search_wine_page1["products"]
    assert isinstance(products, list)
    # If total results < 30 this assertion would need refining; for Vin it is comfortably > 30.
    assert len(products) == 30


def test_C023_search_products_expose_vintage_field(search_wine_page1):
    """Each search-endpoint product carries a `vintage` field — the piece of information that is missing from the catalog endpoint."""
    products = search_wine_page1["products"]
    assert products
    for p in products:
        assert "vintage" in p
        assert p["vintage"] is None or isinstance(p["vintage"], str)


def test_C024_search_products_expose_core_identity_fields(search_wine_page1):
    """Each search product exposes `productId` and `productNumber` — the same keys the catalog endpoint uses."""
    for p in search_wine_page1["products"]:
        assert "productId" in p
        assert "productNumber" in p


def test_C025_search_metadata_has_docCount_totalPages_priceRange(search_wine_page1):
    """`metadata` in the search response contains numeric `docCount`, numeric `totalPages`, and a `priceRange` object with `min` and `max`."""
    m = search_wine_page1["metadata"]
    assert isinstance(m.get("docCount"), int)
    assert isinstance(m.get("totalPages"), int)
    pr = m.get("priceRange")
    assert isinstance(pr, dict)
    assert "min" in pr and "max" in pr
    assert isinstance(pr["min"], (int, float))
    assert isinstance(pr["max"], (int, float))


def test_C026_search_filters_is_array_of_named_filters(search_wine_page1):
    """`filters` in the search response is an array; each filter has `name` (string) and `searchModifiers` (array)."""
    filters = search_wine_page1["filters"]
    assert isinstance(filters, list) and filters
    for f in filters:
        assert isinstance(f.get("name"), str)
        assert isinstance(f.get("searchModifiers"), list)


def test_C027_search_modifier_exposes_value(search_wine_page1):
    """Every entry inside a filter's `searchModifiers` exposes a `value` field — the token a caller passes back as the corresponding query parameter."""
    for f in search_wine_page1["filters"]:
        for m in f["searchModifiers"]:
            assert "value" in m


def test_C028_search_filters_include_country_vintage_assortment(search_wine_page1):
    """The filter set includes at least `Country`, `Vintage`, and `AssortmentText`, the three dimensions most useful for partitioning the catalog in bulk."""
    names = {f["name"] for f in search_wine_page1["filters"]}
    for expected in ("Country", "Vintage", "AssortmentText"):
        assert expected in names, f"filter '{expected}' not in {sorted(names)}"


def test_C029_search_storeId_param_is_silently_ignored(session, api_base):
    """The `storeId` query parameter on the search endpoint is silently ignored — docCount is identical whether it is absent, set to a valid siteId, or set to a bogus value."""
    base = {"categoryLevel1": "Vin", "page": 1}
    r_none = _search(session, api_base, **base)
    r_valid = _search(session, api_base, **base, storeId="0102")
    r_bogus = _search(session, api_base, **base, storeId="not-a-store")
    dc = r_none["metadata"]["docCount"]
    assert r_valid["metadata"]["docCount"] == dc
    assert r_bogus["metadata"]["docCount"] == dc


def test_C030_search_siteId_param_is_silently_ignored(session, api_base):
    """The `siteId` query parameter on the search endpoint is silently ignored."""
    base = {"categoryLevel1": "Vin", "page": 1}
    r_none = _search(session, api_base, **base)
    r_with = _search(session, api_base, **base, siteId="0102")
    assert r_none["metadata"]["docCount"] == r_with["metadata"]["docCount"]


def test_C031_search_country_param_restricts_results(session, api_base):
    """The `country` parameter is a real filter: every returned product has a matching `country` value."""
    r = _search(session, api_base, categoryLevel1="Vin", country="Frankrike", page=1)
    products = r["products"]
    assert products
    for p in products:
        assert p.get("country") == "Frankrike"


def test_C032_search_Vintage_param_restricts_by_year(session, api_base):
    """The `Vintage` parameter is a real filter: every returned product has a matching `vintage` string."""
    r = _search(session, api_base, categoryLevel1="Vin", Vintage="2020", page=1)
    products = r["products"]
    assert products
    for p in products:
        assert p.get("vintage") == "2020"


def test_C033_search_productId_is_string(sample_wine_product):
    """The search endpoint returns `productId` as a JSON string — the same encoding as the catalog endpoint, making the join trivial."""
    assert isinstance(sample_wine_product["productId"], str)


def test_C034_search_exposes_null_vintage_for_non_vintage_wines(session, api_base):
    """A search result can have `vintage` equal to null; non-vintage wines (sparkling, fortified) do not carry a year."""
    for page in range(1, 6):
        r = _search(session, api_base, categoryLevel1="Vin", page=page)
        if any(p.get("vintage") is None for p in r["products"]):
            return
    assert False, "no null-vintage wines found in the first five pages"


def test_C035_search_totalPages_is_capped_below_real_page_count(session, api_base):
    """Without a partitioning filter, `metadata.totalPages` is capped below the real number of pages implied by `docCount` — the Elasticsearch result window prevents paginating through the full result set in one pass."""
    r = _search(session, api_base, categoryLevel1="Vin", page=1)
    m = r["metadata"]
    real_pages = (m["docCount"] + 29) // 30
    assert m["totalPages"] < real_pages, (
        f"expected totalPages ({m['totalPages']}) to be below "
        f"ceil(docCount/30)={real_pages} as a signature of the ES cap"
    )


def test_C036_search_country_partition_fits_within_cap(session, api_base):
    """Partitioning by `country` sidesteps the cap: each country's `totalPages` covers its full `docCount` (no page beyond the capped window is needed)."""
    r = _search(session, api_base, categoryLevel1="Vin", country="Frankrike", page=1)
    m = r["metadata"]
    real_pages = (m["docCount"] + 29) // 30
    assert m["totalPages"] >= real_pages


def test_C038_AssortmentText_filter_enumerates_standard_categories(search_wine_page1):
    """The `AssortmentText` filter enumerates the product-sourcing categories a caller can narrow by; its value set includes at least "Fast sortiment", "Tillfälligt sortiment", and "Ordervaror"."""
    assortment = next(
        (f for f in search_wine_page1["filters"] if f["name"] == "AssortmentText"),
        None,
    )
    assert assortment is not None
    values = {m["value"] for m in assortment["searchModifiers"]}
    for v in ("Fast sortiment", "Tillfälligt sortiment", "Ordervaror"):
        assert v in values, f"missing AssortmentText value: {v!r}; have {values}"


def test_C039_search_AssortmentText_param_filters_results(session, api_base):
    """`AssortmentText` is a real filter: products returned for `AssortmentText=Ordervaror` all carry `assortmentText == "Ordervaror"` in their own record."""
    r = _search(session, api_base, categoryLevel1="Vin", AssortmentText="Ordervaror", page=1)
    products = r["products"]
    assert products
    for p in products:
        assert p.get("assortmentText") == "Ordervaror"


def test_C037_search_no_api_key_returns_401(api_base):
    """The search endpoint, like the catalog, requires the `Ocp-Apim-Subscription-Key` header; missing it yields HTTP 401."""
    resp = requests.get(
        f"{api_base}{SEARCH_PATH}",
        params={"categoryLevel1": "Vin", "page": 1},
        headers={
            "Origin": "https://www.systembolaget.se",
            "Accept": "application/json",
        },
        timeout=30,
    )
    assert resp.status_code == 401


def test_C052_search_totalPages_caps_at_the_10000_result_window(search_wine_page1):
    """For a query whose `docCount` exceeds ~10,000, `metadata.totalPages` is capped at roughly `10000 / pageSize` (333 at page size 30). This is the Elasticsearch `max_result_window` manifesting — generic pagination can physically reach at most ~10,000 results regardless of how many products actually match."""
    m = search_wine_page1["metadata"]
    # Only meaningful when the true result set exceeds the window — wine does.
    assert m["docCount"] > 10000
    reachable = m["totalPages"] * 30
    assert reachable <= 10000, (
        f"expected totalPages*30 <= 10000; got totalPages={m['totalPages']} → "
        f"{reachable} reachable"
    )
    # Tight lower bound to catch drift if Systembolaget raises the window.
    assert reachable >= 9000


def test_C053_search_q_parameter_is_silently_ignored(session, api_base):
    """The `q` query parameter is silently ignored on the search endpoint: `docCount` and the first-page product ids are identical for `q` absent, empty, a real wine term, and random garbage. Free-text search is not supported via this parameter."""
    base = {"categoryLevel1": "Vin", "page": 1}
    variants = [
        _search(session, api_base, **base),
        _search(session, api_base, **base, q=""),
        _search(session, api_base, **base, q="barolo"),
        _search(session, api_base, **base, q="asdfxyz-nonsense-12345"),
    ]
    doc_counts = {r["metadata"]["docCount"] for r in variants}
    assert len(doc_counts) == 1, f"docCount varied across q values: {doc_counts}"

    ids = [tuple(p["productNumber"] for p in r["products"]) for r in variants]
    assert len(set(ids)) == 1, (
        "first-page products differ across q values — q may be partially honoured"
    )


def test_C054_country_partition_row_count_equals_docCount(sverige_wines, session, api_base):
    """Iterating all pages of a country-partitioned wine search returns exactly `metadata.docCount` result rows. These rows are **not deduplicated by the server** — a small fraction of productNumbers typically appears on more than one page, so the number of unique products is less than or equal to docCount. Callers that want a unique-product set must dedup on the client."""
    meta_resp = session.get(
        f"{api_base}{SEARCH_PATH}",
        params={"categoryLevel1": "Vin", "country": "Sverige", "page": 1},
        timeout=30,
    ).json()
    expected = meta_resp["metadata"]["docCount"]

    numbers = [p["productNumber"] for p in sverige_wines]
    unique = set(numbers)
    # Row count matches docCount exactly.
    assert len(numbers) == expected, (
        f"collected {len(numbers)} rows but docCount was {expected}"
    )
    # Dedup is at the client — uniques may be less than row count.
    assert len(unique) <= len(numbers)
