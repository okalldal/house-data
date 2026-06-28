"""
Probes for the postcode → home-delivery endpoint.

GET /v1/postalCode/{code} maps a Swedish 5-digit postcode to the depot
that serves home deliveries to that postcode, and reports whether home
delivery is even applicable there. Systembolaget.se uses this endpoint
to gate the home-delivery flow before checkout.

The endpoint is the missing link between a customer's postcode and the
/v1/stockbalance/depot/{depotId}/{productId} inventory — i.e., "can I
order this wine delivered to my door?".
"""

import pytest


def _postal_code(session, api_base, code: str):
    return session.get(
        f"{api_base}/sb-api-ecommerce/v1/postalCode/{code}",
        timeout=30,
    )


def test_C120_postalCode_endpoint_returns_200_for_valid_code(session, api_base):
    """C120: /v1/postalCode/{code} returns 200 for a valid Stockholm postcode."""
    r = _postal_code(session, api_base, "11454")
    assert r.status_code == 200, r.text


def test_C121_postalCode_response_has_delivery_fields(session, api_base):
    """C121: Response carries postalCity, homeOrderApplicable, depotStockId."""
    body = _postal_code(session, api_base, "11454").json()
    for key in ("postalCode", "postalCity", "homeOrderApplicable", "depotStockId"):
        assert key in body, (key, list(body))
    assert isinstance(body["homeOrderApplicable"], bool)
    assert isinstance(body["depotStockId"], str) and body["depotStockId"].isdigit()


def test_C122_postalCode_supports_space_separated_form(session, api_base):
    """C122: Both '11454' and '114 54' resolve to the same record."""
    a = _postal_code(session, api_base, "11454").json()
    b = _postal_code(session, api_base, "114 54").json()
    assert a["postalCode"] == b["postalCode"]
    assert a["depotStockId"] == b["depotStockId"]


def test_C123_postalCode_404_for_unassigned_code(session, api_base):
    """C123: Unassigned 5-digit codes return 404, not 200 with null fields."""
    r = _postal_code(session, api_base, "00000")
    assert r.status_code == 404


def test_C124_postalCode_400_for_wrong_length(session, api_base):
    """C124: Non-5-char postcodes return 400 with a validation message."""
    r = _postal_code(session, api_base, "0")
    assert r.status_code == 400


def test_C125_depotStockId_matches_all_store_depots(session, api_base, sample_wine_product, all_store_stock):
    """C125: depotStockId from postalCode is one of store.depotStockId on the
    all-store endpoint — the same identifier space."""
    stockholm_depot = _postal_code(session, api_base, "11454").json()["depotStockId"]
    all_depots = {
        (e.get("store") or {}).get("depotStockId")
        for e in all_store_stock["storeStocks"]
    }
    all_depots.discard(None)
    assert stockholm_depot in all_depots, (stockholm_depot, sorted(all_depots))


def test_C126_postalCode_depotStockId_is_valid_depot_stock_id(session, api_base, sample_wine_product):
    """C126: depotStockId from postalCode works as depotId on
    /v1/stockbalance/depot/{depotId}/{productId}."""
    depot = _postal_code(session, api_base, "11454").json()["depotStockId"]
    pid = sample_wine_product["productId"]
    r = session.get(
        f"{api_base}/sb-api-ecommerce/v1/stockbalance/depot/{depot}/{pid}",
        timeout=30,
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["depotId"] == depot
    assert body["productId"] == pid
    assert isinstance(body["stock"], int)


def test_C127_postalCode_different_regions_map_to_different_depots(session, api_base):
    """C127: Postcodes in different regions can resolve to different depots —
    depot is geographic, not a single national warehouse."""
    stockholm = _postal_code(session, api_base, "11454").json()["depotStockId"]
    kiruna = _postal_code(session, api_base, "98131").json()["depotStockId"]
    assert stockholm != kiruna
