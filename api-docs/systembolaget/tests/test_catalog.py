"""
Probes for the catalog endpoint: GET /sb-api-ecommerce/v1/product

Each test's first docstring line is the claim it establishes.
"""

import requests


def test_C001_catalog_endpoint_returns_200(session, api_base):
    """The catalog endpoint GET /sb-api-ecommerce/v1/product returns HTTP 200 with the standard auth + Origin + Accept headers."""
    resp = session.get(f"{api_base}/sb-api-ecommerce/v1/product", timeout=60)
    assert resp.status_code == 200


def test_C002_catalog_response_is_json_array(catalog):
    """The catalog endpoint response body is a JSON array at the top level, not wrapped in an enclosing object."""
    assert isinstance(catalog, list)
    assert len(catalog) > 0


def test_C003_missing_subscription_key_returns_401(api_base):
    """Requests to the catalog endpoint without an Ocp-Apim-Subscription-Key header are rejected with HTTP 401."""
    resp = requests.get(
        f"{api_base}/sb-api-ecommerce/v1/product",
        headers={
            "Origin": "https://www.systembolaget.se",
            "Accept": "application/json",
        },
        timeout=30,
    )
    assert resp.status_code == 401


def test_C004_catalog_items_have_core_identity_fields(catalog):
    """Every catalog item is an object carrying productNumber, productId, and categoryLevel1."""
    assert len(catalog) > 0
    for item in catalog:
        assert isinstance(item, dict)
        assert "productNumber" in item
        assert "productId" in item
        assert "categoryLevel1" in item


def test_C005_catalog_categoryLevel1_partitions_product_kinds(catalog):
    """`categoryLevel1` is the top-level product-kind partition; its values include at least "Vin" and "Sprit"."""
    categories = {item.get("categoryLevel1") for item in catalog}
    assert "Vin" in categories
    assert "Sprit" in categories


def test_C006_catalog_wine_items_have_no_vintage_field(catalog):
    """Catalog items classified as `Vin` expose no `vintage` key — vintage is only available via the search endpoint."""
    wine_items = [item for item in catalog if item.get("categoryLevel1") == "Vin"]
    assert len(wine_items) > 0
    for item in wine_items:
        assert "vintage" not in item, (
            f"catalog item {item.get('productNumber')} unexpectedly has vintage={item.get('vintage')!r}"
        )


def test_C007_catalog_is_a_sparse_index(catalog):
    """The catalog is a sparse index: every item exposes exactly the keys productNumber, productId, categoryLevel1, productNameBold, imageUrl, isHidden, isSearchable, lastModified — no price, stock, vintage, producer, country, or other product-detail fields."""
    expected = {
        "productNumber", "productId", "categoryLevel1", "productNameBold",
        "imageUrl", "isHidden", "isSearchable", "lastModified",
    }
    assert len(catalog) > 0
    for item in catalog:
        assert set(item.keys()) == expected, (
            f"item {item.get('productNumber')} has unexpected key set: "
            f"{sorted(item.keys())}"
        )


def test_C008_catalog_identity_fields_are_json_strings(catalog):
    """Both `productNumber` and `productId` in the catalog are encoded as JSON strings, not numbers."""
    assert len(catalog) > 0
    for item in catalog:
        assert isinstance(item["productNumber"], str)
        assert isinstance(item["productId"], str)


def test_C009_catalog_productNumber_is_unique(catalog):
    """`productNumber` is unique within the catalog — the response contains one entry per SKU."""
    numbers = [item["productNumber"] for item in catalog]
    assert len(numbers) == len(set(numbers))


def test_C010_catalog_categoryLevel1_can_be_null(catalog):
    """Some catalog items have `categoryLevel1` set to null — callers filtering by category must handle a None value, not assume every item is categorised."""
    null_items = [item for item in catalog if item.get("categoryLevel1") is None]
    assert len(null_items) > 0


def test_C011_wine_productNumbers_form_sibling_groups(catalog):
    """The last two characters of a wine `productNumber` encode a packaging/size variant: many wines share the first N-2 characters with one or more siblings. The catalog consistently exposes tens or hundreds of such sibling groups — this is a stable, structural property, not a rare edge case."""
    from collections import defaultdict
    wines = [item for item in catalog if item.get("categoryLevel1") == "Vin"]
    groups = defaultdict(list)
    for item in wines:
        pn = item["productNumber"]
        groups[pn[:-2]].append(pn)

    multi = [pns for pns in groups.values() if len(pns) > 1]
    # At least 50 multi-member groups exist — this has been consistently in
    # the hundreds when observed, so 50 is a very loose lower bound.
    assert len(multi) >= 50, (
        f"expected many wine sibling groups; found {len(multi)}"
    )


def test_C012_siblings_usually_but_not_always_share_productNameBold(catalog):
    """Within a wine sibling group, `productNameBold` is **usually** but not always shared across members — siblings are typically the same wine packaged differently, but a small minority of prefix-sharing groups are unrelated products that happen to collide numerically. At least 80% of multi-member wine groups share a single name; at the same time some mixed-name groups do exist. Treat the last-two-digit suffix as a heuristic for "same wine", not as a guarantee."""
    from collections import defaultdict
    wines = [item for item in catalog if item.get("categoryLevel1") == "Vin"]
    groups = defaultdict(list)
    for item in wines:
        groups[item["productNumber"][:-2]].append(item)

    multi_groups = [g for g in groups.values() if len(g) > 1]
    assert multi_groups, "no sibling groups found"

    single_name = [g for g in multi_groups
                   if len({i.get("productNameBold") for i in g}) == 1]
    mixed_name = [g for g in multi_groups
                  if len({i.get("productNameBold") for i in g}) > 1]

    # Usually share: the heuristic is useful.
    assert len(single_name) / len(multi_groups) >= 0.80, (
        f"only {len(single_name)}/{len(multi_groups)} sibling groups share a "
        f"single name — the heuristic has degraded below 80%"
    )
    # But not always: confirm the claim isn't over-stated.
    assert mixed_name, (
        "every sibling group shares a name — the claim that mixed-name groups "
        "exist is now too strong; rewrite to assert a strict invariant"
    )
