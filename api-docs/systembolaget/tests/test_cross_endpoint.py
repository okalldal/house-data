"""
Cross-endpoint / interop probes. These claims are about how data on one
endpoint relates to data on another — essential for building applications
that combine them.

Each test's first docstring line is the claim it establishes.
"""

SEARCH_PATH = "/sb-api-ecommerce/v1/productsearch/search"
CATALOG_PATH = "/sb-api-ecommerce/v1/product"


def test_C080_productId_joins_catalog_and_search(session, api_base, catalog, sample_wine_product):
    """`productId` is consistent across the catalog and search endpoints: looking up a search product's `productNumber` in the catalog yields an item with the same `productId`."""
    by_number = {item["productNumber"]: item for item in catalog}
    catalog_match = by_number.get(sample_wine_product["productNumber"])
    assert catalog_match is not None, (
        f"sample wine {sample_wine_product['productNumber']} not in catalog"
    )
    assert catalog_match["productId"] == sample_wine_product["productId"]


def test_C081_search_productNumber_always_exists_in_catalog(session, api_base, catalog):
    """Every `productNumber` returned by the search endpoint also exists in the catalog response — the search index does not include entries that the catalog omits."""
    resp = session.get(
        f"{api_base}{SEARCH_PATH}",
        params={"categoryLevel1": "Vin", "page": 1},
        timeout=30,
    )
    resp.raise_for_status()
    search_numbers = {p["productNumber"] for p in resp.json()["products"]}
    catalog_numbers = {item["productNumber"] for item in catalog}
    missing = search_numbers - catalog_numbers
    assert not missing, f"search products missing from catalog: {missing}"


def test_C082_catalog_wider_than_search_for_wine(session, api_base, catalog):
    """The catalog (all product kinds) is larger than the wine search docCount — a catalog response contains non-wine entries the search endpoint wouldn't return for `categoryLevel1=Vin`."""
    resp = session.get(
        f"{api_base}{SEARCH_PATH}",
        params={"categoryLevel1": "Vin", "page": 1},
        timeout=30,
    )
    resp.raise_for_status()
    wine_doc_count = resp.json()["metadata"]["docCount"]
    assert len(catalog) > wine_doc_count


def test_C083_all_store_productId_matches_requested(session, api_base, sample_wine_product):
    """Every `stockBalance.productId` in an all-store response matches the productId in the URL — the endpoint does not leak data for other products."""
    pid = sample_wine_product["productId"]
    resp = session.get(
        f"{api_base}/sb-api-ecommerce/v1/site/stores/{pid}/",
        timeout=60,
    )
    resp.raise_for_status()
    for entry in resp.json()["storeStocks"]:
        assert entry["stockBalance"]["productId"] == pid
