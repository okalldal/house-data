"""
Probes for the /sold endpoint — past home sales in Sweden.

These are AUTHENTICATED probes: they need a real Booli identity and skip
cleanly unless BOOLI_CALLER_ID and BOOLI_KEY are set (see conftest and
STRATEGY.md). Until then the claims below are PENDING in api.md — grounded on
Booli's published Open API schema but not yet confirmed against the live API
from this repo.

Each test's first docstring line is the claim it establishes.
"""

from conftest import requires_credentials


@requires_credentials
def test_B010_auth_hash_construction_is_accepted(signed):
    """The hash construction sha1(callerId + time + unique + key) is accepted: a correctly signed /sold request returns HTTP 200, confirming the auth algorithm in conftest.auth_params."""
    resp = signed("sold", areaId=76208, limit=1)
    assert resp.status_code == 200


@requires_credentials
def test_B011_sold_response_is_object_with_count_and_array(sold_page):
    """A /sold response is a JSON object exposing an integer `totalCount`, an integer `count`, and a `sold` array."""
    assert isinstance(sold_page, dict)
    assert isinstance(sold_page.get("totalCount"), int)
    assert isinstance(sold_page.get("count"), int)
    assert isinstance(sold_page.get("sold"), list)


@requires_credentials
def test_B012_sold_items_expose_core_sale_fields(sold_page):
    """Each /sold item exposes the core sale facts: `booliId`, `soldPrice`, `soldDate`, and `objectType`."""
    items = sold_page["sold"]
    assert items, "expected at least one sold item for the sample kommun"
    for item in items:
        assert "booliId" in item
        assert "soldPrice" in item
        assert "soldDate" in item
        assert "objectType" in item


@requires_credentials
def test_B013_sold_price_is_numeric_kronor(sold_page):
    """`soldPrice` is a positive number — the final transaction price in SEK."""
    for item in sold_page["sold"]:
        price = item["soldPrice"]
        assert isinstance(price, (int, float))
        assert price > 0


@requires_credentials
def test_B014_sold_date_is_iso_yyyy_mm_dd(sold_page):
    """`soldDate` is an ISO `YYYY-MM-DD` date string."""
    import re

    for item in sold_page["sold"]:
        assert re.fullmatch(r"\d{4}-\d{2}-\d{2}", item["soldDate"]), item["soldDate"]


@requires_credentials
def test_B015_sold_items_carry_location_with_position(sold_page):
    """Each /sold item carries a `location` object with a `position` exposing numeric `latitude` and `longitude`."""
    for item in sold_page["sold"]:
        loc = item.get("location")
        assert isinstance(loc, dict)
        pos = loc.get("position")
        assert isinstance(pos, dict)
        assert isinstance(pos.get("latitude"), (int, float))
        assert isinstance(pos.get("longitude"), (int, float))


@requires_credentials
def test_B016_limit_param_caps_page_size(signed):
    """The `limit` query parameter caps the number of returned items per page (here, <= 10)."""
    resp = signed("sold", areaId=76208, limit=10)
    resp.raise_for_status()
    data = resp.json()
    assert len(data["sold"]) <= 10


@requires_credentials
def test_B017_offset_param_pages_through_results(signed):
    """`offset` pages through the result set: page two (offset=10) returns different booliIds than page one."""
    p1 = signed("sold", areaId=76208, limit=10, offset=0).json()["sold"]
    p2 = signed("sold", areaId=76208, limit=10, offset=10).json()["sold"]
    ids1 = {i["booliId"] for i in p1}
    ids2 = {i["booliId"] for i in p2}
    assert ids1 and ids2
    assert ids1.isdisjoint(ids2)
