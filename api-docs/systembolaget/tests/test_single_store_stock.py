"""
Probes for the single-store stock endpoint:
    GET /sb-api-ecommerce/v1/stockbalance/store/{siteId}/{productId}

Each test's first docstring line is the claim it establishes.
"""

STOCK_PATH = "/sb-api-ecommerce/v1/stockbalance/store"


def _single_stock(session, api_base, site_id, product_id):
    resp = session.get(
        f"{api_base}{STOCK_PATH}/{site_id}/{product_id}",
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json()


def test_C060_single_store_endpoint_returns_200(session, api_base, sample_store_with_stock):
    """The single-store stock endpoint `/v1/stockbalance/store/{siteId}/{productId}` returns HTTP 200 for a valid (store, product) pair."""
    site_id = sample_store_with_stock["store"]["siteId"]
    product_id = sample_store_with_stock["stockBalance"]["productId"]
    resp = session.get(f"{api_base}{STOCK_PATH}/{site_id}/{product_id}", timeout=30)
    assert resp.status_code == 200


def test_C061_single_store_response_has_stock_assortment_shelf(session, api_base, sample_store_with_stock):
    """The single-store response is a small JSON object exposing `stock`, `isInStoreAssortment`, and `shelf`."""
    site_id = sample_store_with_stock["store"]["siteId"]
    product_id = sample_store_with_stock["stockBalance"]["productId"]
    data = _single_stock(session, api_base, site_id, product_id)
    assert "stock" in data
    assert "isInStoreAssortment" in data
    assert "shelf" in data


def test_C062_single_store_stock_is_int_and_assortment_is_bool(session, api_base, sample_store_with_stock):
    """On the single-store endpoint, `stock` is an integer and `isInStoreAssortment` is a boolean."""
    site_id = sample_store_with_stock["store"]["siteId"]
    product_id = sample_store_with_stock["stockBalance"]["productId"]
    data = _single_stock(session, api_base, site_id, product_id)
    assert isinstance(data["stock"], int)
    assert isinstance(data["isInStoreAssortment"], bool)


def test_C063_single_store_shelf_is_string_or_null(session, api_base, sample_store_with_stock):
    """The `shelf` field is either a string (aisle/location code) or null; null has been observed even when stock > 0."""
    site_id = sample_store_with_stock["store"]["siteId"]
    product_id = sample_store_with_stock["stockBalance"]["productId"]
    data = _single_stock(session, api_base, site_id, product_id)
    assert data["shelf"] is None or isinstance(data["shelf"], str)


def test_C064_single_store_agrees_with_all_store_endpoint(session, api_base, sample_store_with_stock):
    """The single-store `stock` value agrees with the matching entry in the all-store response at the same moment, confirming the two endpoints read from the same underlying stock data."""
    site_id = sample_store_with_stock["store"]["siteId"]
    product_id = sample_store_with_stock["stockBalance"]["productId"]
    expected_stock = sample_store_with_stock["stockBalance"]["stock"]
    data = _single_stock(session, api_base, site_id, product_id)
    # Stock can shift between calls; accept a small tolerance for concurrent sales.
    assert abs(data["stock"] - expected_stock) <= 2, (
        f"stock drift too large: single={data['stock']} vs all-store={expected_stock}"
    )


def test_C065_ordervaror_can_have_store_stock_despite_not_in_assortment(session, api_base):
    """"Ordervaror" products — not in any store's regular assortment (`isInStoreAssortment=false`) — can still have `stock > 0` at some stores. The two signals (`isInStoreAssortment` and `stock`) are independent. The probe searches across multiple pages of the Ordervaror partition, fetching all-store availability for each candidate until it finds one store that has physical stock of an Ordervaror item; the claim passes as soon as one such instance is confirmed via the single-store endpoint."""
    MAX_PAGES = 5          # 150 candidate products
    MAX_PRODUCTS_TRIED = 40  # hard ceiling on all-store fetches

    tried = 0
    any_stocked_store_ever = False
    for page in range(1, MAX_PAGES + 1):
        search_resp = session.get(
            f"{api_base}/sb-api-ecommerce/v1/productsearch/search",
            params={"categoryLevel1": "Vin", "AssortmentText": "Ordervaror", "page": page},
            timeout=30,
        )
        search_resp.raise_for_status()
        candidates = search_resp.json().get("products", [])
        if not candidates:
            break

        for prod in candidates:
            if tried >= MAX_PRODUCTS_TRIED:
                break
            tried += 1

            pid = prod["productId"]
            allstore_resp = session.get(
                f"{api_base}/sb-api-ecommerce/v1/site/stores/{pid}/",
                timeout=60,
            )
            allstore_resp.raise_for_status()
            stocked_entries = [
                e for e in allstore_resp.json()["storeStocks"]
                if e["stockBalance"]["stock"] > 0
            ]
            if not stocked_entries:
                continue
            any_stocked_store_ever = True

            # Pick the one with the most stock — least likely to have sold out
            # between the all-store call and the single-store confirmation.
            entry = max(stocked_entries, key=lambda e: e["stockBalance"]["stock"])
            site_id = entry["store"]["siteId"]
            single = _single_stock(session, api_base, site_id, pid)
            if single["stock"] > 0 and single["isInStoreAssortment"] is False:
                return  # claim confirmed

        if tried >= MAX_PRODUCTS_TRIED:
            break

    # Failure path carries diagnostics so a regression is actionable.
    raise AssertionError(
        f"tried {tried} Ordervaror products across {MAX_PAGES} pages; "
        f"any_stocked_store_ever={any_stocked_store_ever}. "
        f"No product had a store with stock>0 AND isInStoreAssortment=False — "
        f"either the two signals are no longer independent, or the sample needs widening."
    )
