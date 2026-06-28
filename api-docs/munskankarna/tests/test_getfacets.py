"""
Probes for the facet-enumeration endpoint:
    GET /umbraco/surface/winesearch/getfacets/

Each test's first docstring line is the claim it establishes.
"""

import requests

FACETS_PATH = "/umbraco/surface/winesearch/getfacets/"


def test_M001_getfacets_endpoint_returns_200(session, api_base):
    """The facets endpoint returns HTTP 200 with a JSON body for a plain GET (no body, no auth)."""
    resp = session.get(f"{api_base}{FACETS_PATH}", timeout=30)
    assert resp.status_code == 200
    assert resp.headers.get("Content-Type", "").startswith("application/json")


def test_M002_getfacets_is_get_only(session, api_base):
    """Only GET is supported on the facets endpoint: POST returns HTTP 404."""
    resp = session.post(f"{api_base}{FACETS_PATH}", data={}, timeout=30)
    assert resp.status_code == 404


def test_M003_getfacets_response_has_top_level_facets_object(facets_response):
    """The facets response is a JSON object with a single top-level key `facets` mapping to an object."""
    assert isinstance(facets_response, dict)
    assert list(facets_response.keys()) == ["facets"]
    assert isinstance(facets_response["facets"], dict)


def test_M004_getfacets_exposes_expected_facet_categories(facets_response):
    """`facets` exposes at least the categories used by downstream code: categoryName, country, region, importer, rating, grapeTypes, price, producer, wineBottleActivityName, wineBottleActivityType."""
    expected = {
        "categoryName",
        "country",
        "region",
        "importer",
        "rating",
        "grapeTypes",
        "price",
        "producer",
        "wineBottleActivityName",
        "wineBottleActivityType",
    }
    got = set(facets_response["facets"].keys())
    missing = expected - got
    assert not missing, f"missing facet categories: {missing}; have {sorted(got)}"


def test_M005_facet_entries_use_item1_item4_tuple_shape(facets_response):
    """Every facet entry is a JSON object with keys item1, item2, item3, item4 — a generic C#-tuple serialisation shared across facet categories."""
    for category, entries in facets_response["facets"].items():
        assert isinstance(entries, list), f"{category} is not a list"
        if not entries:
            continue
        for e in entries:
            assert set(e.keys()) == {"item1", "item2", "item3", "item4"}, (
                f"unexpected keys in {category}[{e}]"
            )


def test_M006_activity_name_facet_exposes_session_keys(facets_response):
    """`facets.wineBottleActivityName[*].item2` is the session key to pass back as `wineBottleActivityName[]` on `listwinebottles/`; it has the `YYYYMMDD-<label>` form."""
    activities = facets_response["facets"]["wineBottleActivityName"]
    assert activities, "expected a non-empty activity list"
    for a in activities:
        key = a["item2"]
        assert isinstance(key, str) and key, f"non-string item2: {a!r}"
        # Sanity-check the shape: leading 8-digit date, then a dash, then a label.
        prefix, sep, label = key.partition("-")
        assert sep == "-" and prefix.isdigit() and len(prefix) == 8, (
            f"unexpected session-key format: {key!r}"
        )
        assert label, f"missing label in session key: {key!r}"


def test_M007_activity_name_facet_includes_hundreds_of_sessions(facets_response):
    """The activity-name facet enumerates the full historical session archive — hundreds of entries, growing as new tastings are published."""
    activities = facets_response["facets"]["wineBottleActivityName"]
    assert len(activities) >= 500, f"expected >=500 activity entries, got {len(activities)}"


def test_M008_activity_type_facet_exposes_assortment_buckets(facets_response):
    """`facets.wineBottleActivityType[*].item1` enumerates the high-level session buckets and includes at least "Fast sortiment", "Tillfälligt sortiment", "Hitlista", "Temaprovning", and "Ordervaror på Systembolaget"."""
    types = facets_response["facets"]["wineBottleActivityType"]
    labels = {t["item1"] for t in types}
    for expected in (
        "Fast sortiment",
        "Tillfälligt sortiment",
        "Hitlista",
        "Temaprovning",
        "Ordervaror på Systembolaget",
    ):
        assert expected in labels, f"missing activity-type label {expected!r}; have {labels}"
