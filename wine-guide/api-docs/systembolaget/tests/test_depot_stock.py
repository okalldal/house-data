"""
Probes for the depot stock endpoint:
    GET /sb-api-ecommerce/v1/stockbalance/depot/{depotId}/{productId}

This is the endpoint the site calls to show home-delivery ("Hemleverans")
and pickup availability — it reflects central-warehouse inventory rather
than per-store shelves.

Each test's first docstring line is the claim it establishes.
"""

DEPOT_PATH = "/sb-api-ecommerce/v1/stockbalance/depot"


def _depot_stock(session, api_base, depot_id, product_id):
    resp = session.get(
        f"{api_base}{DEPOT_PATH}/{depot_id}/{product_id}",
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json()


def test_C100_depot_endpoint_returns_200(session, api_base, sample_wine_product, all_store_stock):
    """The depot stock endpoint `/v1/stockbalance/depot/{depotId}/{productId}` returns HTTP 200 when called with a depotId taken from the all-store response."""
    pid = sample_wine_product["productId"]
    depot = all_store_stock["storeStocks"][0]["store"]["depotStockId"]
    resp = session.get(f"{api_base}{DEPOT_PATH}/{depot}/{pid}", timeout=30)
    assert resp.status_code == 200


def test_C101_depot_response_shape(session, api_base, sample_wine_product, all_store_stock):
    """The depot response is a small JSON object with exactly the keys `productId`, `depotId`, and `stock` (integer); no shelf or assortment data."""
    pid = sample_wine_product["productId"]
    depot = all_store_stock["storeStocks"][0]["store"]["depotStockId"]
    data = _depot_stock(session, api_base, depot, pid)
    assert set(data.keys()) == {"productId", "depotId", "stock"}
    assert isinstance(data["productId"], str)
    assert isinstance(data["depotId"], str)
    assert isinstance(data["stock"], int)


def test_C102_depot_echoes_url_parameters(session, api_base, sample_wine_product, all_store_stock):
    """The depot response echoes the URL's `productId` and `depotId` — values returned match the path parameters, not some upstream identifier."""
    pid = sample_wine_product["productId"]
    depot = all_store_stock["storeStocks"][0]["store"]["depotStockId"]
    data = _depot_stock(session, api_base, depot, pid)
    assert data["productId"] == pid
    assert data["depotId"] == depot
