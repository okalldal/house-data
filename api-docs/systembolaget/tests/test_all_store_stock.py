"""
Probes for the all-store stock endpoint:
    GET /sb-api-ecommerce/v1/site/stores/{productId}/

Each test's first docstring line is the claim it establishes.
"""

ALL_STORE_PATH = "/sb-api-ecommerce/v1/site/stores"


def test_C040_all_store_endpoint_returns_200(session, api_base, sample_wine_product):
    """The all-store stock endpoint `/v1/site/stores/{productId}/` returns HTTP 200 for a valid productId."""
    pid = sample_wine_product["productId"]
    resp = session.get(f"{api_base}{ALL_STORE_PATH}/{pid}/", timeout=60)
    assert resp.status_code == 200


def test_C041_all_store_response_has_totalNumberOfStores_and_storeStocks(all_store_stock):
    """The response carries `totalNumberOfStores` (int) and `storeStocks` (array) at the top level."""
    assert isinstance(all_store_stock.get("totalNumberOfStores"), int)
    assert isinstance(all_store_stock.get("storeStocks"), list)


def test_C042_all_store_stocks_pair_store_and_stockBalance(all_store_stock):
    """Each entry in `storeStocks` is an object containing a `store` record and a `stockBalance` record."""
    entries = all_store_stock["storeStocks"]
    assert entries
    for entry in entries:
        assert isinstance(entry.get("store"), dict)
        assert isinstance(entry.get("stockBalance"), dict)


def test_C043_all_store_store_object_has_identity_fields(all_store_stock):
    """Each `store` object carries at minimum siteId, alias, address, city, county, postalCode."""
    for entry in all_store_stock["storeStocks"]:
        s = entry["store"]
        for key in ("siteId", "alias", "address", "city", "county", "postalCode"):
            assert key in s, f"missing `{key}` on store record"


def test_C044_all_store_stockBalance_has_core_fields(all_store_stock):
    """Each `stockBalance` object exposes integer `stock`, string `productId`, string `storeId`, and `shelf` which is either a string or null (null is observed even when stock > 0)."""
    for entry in all_store_stock["storeStocks"]:
        sb = entry["stockBalance"]
        assert isinstance(sb.get("stock"), int)
        assert isinstance(sb.get("productId"), str)
        assert isinstance(sb.get("storeId"), str)
        assert sb.get("shelf") is None or isinstance(sb["shelf"], str)


def test_C045_all_store_totalNumberOfStores_matches_list_length(all_store_stock):
    """`totalNumberOfStores` equals the length of `storeStocks` — it counts the entries returned, not the catalog-wide store population."""
    assert all_store_stock["totalNumberOfStores"] == len(all_store_stock["storeStocks"])


def test_C046_all_store_returns_hundreds_of_stores(all_store_stock):
    """The all-store endpoint returns an entry for every Systembolaget location — expect several hundred stores in a single call."""
    assert len(all_store_stock["storeStocks"]) >= 400


def test_C047_all_store_stock_join_keys_are_consistent(all_store_stock):
    """Within a response, each `stockBalance.storeId` equals the sibling `store.siteId` — the two sub-objects share the same site identifier."""
    for entry in all_store_stock["storeStocks"]:
        assert entry["stockBalance"]["storeId"] == entry["store"]["siteId"]


def test_C048_all_store_records_carry_operational_flags(all_store_stock):
    """Each `store` record exposes operational booleans — at minimum `isActive`, `isOpen`, `isBlocked`, `isDepot`, `isStore`, `isTastingStore`, `isFullAssortmentOrderStore`, plus a `depotStockId` string pointing to the store's supplying depot."""
    for entry in all_store_stock["storeStocks"]:
        s = entry["store"]
        for flag in ("isActive", "isOpen", "isBlocked", "isDepot", "isStore",
                     "isTastingStore", "isFullAssortmentOrderStore"):
            assert isinstance(s.get(flag), bool), f"missing/non-bool {flag}"
        assert isinstance(s.get("depotStockId"), str)


def test_C049_all_store_isStore_is_always_false(all_store_stock):
    """Despite the field name, `isStore` is always `false` across the all-store response. The flag does not distinguish stores from other sites here — treat it as uninformative and rely on `isDepot`, `isTastingStore`, and `isAgent` (from sitesearch) instead."""
    for entry in all_store_stock["storeStocks"]:
        assert entry["store"]["isStore"] is False


def test_C050_all_store_isDepot_is_always_false(all_store_stock):
    """`isDepot` is always false on this endpoint — it returns only stores, never depot entries. Depot stock lives behind the separate `/stockbalance/depot/{depotId}/{productId}` endpoint."""
    for entry in all_store_stock["storeStocks"]:
        assert entry["store"]["isDepot"] is False


def test_C051_all_store_depotStockId_maps_many_stores_to_few_depots(all_store_stock):
    """`depotStockId` is shared among many stores — Sweden is served by a handful of central depots, not one per store."""
    depots = {e["store"]["depotStockId"] for e in all_store_stock["storeStocks"]}
    stores = len(all_store_stock["storeStocks"])
    # Far fewer depots than stores.
    assert len(depots) < stores / 20
    assert len(depots) >= 1
