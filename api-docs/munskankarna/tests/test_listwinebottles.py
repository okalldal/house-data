"""
Probes for the tasting-note listing endpoint:
    POST /umbraco/surface/winesearch/listwinebottles/

Each test's first docstring line is the claim it establishes.
"""

from collections import Counter

import requests

from conftest import post_list

LIST_PATH = "/umbraco/surface/winesearch/listwinebottles/"


def test_M020_listwinebottles_endpoint_returns_200_for_minimal_post(session, api_base):
    """A minimal form-encoded POST to `listwinebottles/` returns HTTP 200 with a JSON body — no auth or body is strictly required."""
    resp = session.post(f"{api_base}{LIST_PATH}", data={}, timeout=30)
    assert resp.status_code == 200
    assert resp.headers.get("Content-Type", "").startswith("application/json")


def test_M021_listwinebottles_is_post_only(session, api_base):
    """GET on `listwinebottles/` returns HTTP 404 — this endpoint is POST-only."""
    resp = session.get(f"{api_base}{LIST_PATH}", timeout=30)
    assert resp.status_code == 404


def test_M022_listwinebottles_accepts_json_body(session, api_base):
    """The endpoint accepts a JSON body in addition to `application/x-www-form-urlencoded` — both return the same shape of response."""
    resp = session.post(
        f"{api_base}{LIST_PATH}",
        json={"pageIndex": 0, "pageSize": 3, "sortOrder": ""},
        timeout=30,
    )
    assert resp.status_code == 200
    body = resp.json()
    assert "result" in body and "total" in body


def test_M023_listwinebottles_response_has_result_total_facets(stable_session_small_rows):
    """A `listwinebottles` response is a JSON object whose top-level keys include `result` (array), `total` (int), and `facets` (object)."""
    body = stable_session_small_rows
    assert isinstance(body, dict)
    assert isinstance(body.get("result"), list)
    assert isinstance(body.get("total"), int)
    assert isinstance(body.get("facets"), dict)


def test_M024_listwinebottles_rows_expose_documented_fields(stable_session_small_rows):
    """Every row in `result` exposes the full field set consumed by `scrape_wines.flatten()` — wineBottleName, wineBottleYearName, wineBottleCategoryName, wineBottleCountryName, wineBottleCountryAlias, wineBottleRegionName, wineBottleSubRegionName, wineBottleProducerName, wineBottleImporter, wineBottlePrice, wineBottleVolume, wineBottleAlcohol, wineBottleSugarContent, wineBottleRatePoints, wineBottleRateText, wineBottleRateIsTypical, wineBottleRateCanBeStored, wineBottleRateCategorySymbol, wineBottleRawMaterials, wineBottleActivityName, wineBottleActivityPublishDate, wineBottleActivityUrl, wineBottleUrl, wineBottleExternalLink."""
    expected = {
        "wineBottleName",
        "wineBottleYearName",
        "wineBottleCategoryName",
        "wineBottleCountryName",
        "wineBottleCountryAlias",
        "wineBottleRegionName",
        "wineBottleSubRegionName",
        "wineBottleProducerName",
        "wineBottleImporter",
        "wineBottlePrice",
        "wineBottleVolume",
        "wineBottleAlcohol",
        "wineBottleSugarContent",
        "wineBottleRatePoints",
        "wineBottleRateText",
        "wineBottleRateIsTypical",
        "wineBottleRateCanBeStored",
        "wineBottleRateCategorySymbol",
        "wineBottleRawMaterials",
        "wineBottleActivityName",
        "wineBottleActivityPublishDate",
        "wineBottleActivityUrl",
        "wineBottleUrl",
        "wineBottleExternalLink",
    }
    rows = stable_session_small_rows["result"]
    assert rows
    for row in rows:
        missing = expected - set(row.keys())
        assert not missing, f"row missing fields {missing}: {row}"


def test_M025_numeric_fields_are_json_strings(stable_session_small_rows):
    """Several nominally numeric fields — `wineBottlePrice`, `wineBottleVolume`, `wineBottleAlcohol`, `wineBottleSugarContent`, `wineBottleYearName` — are returned as JSON strings. Callers must parse them before arithmetic."""
    string_fields = (
        "wineBottlePrice",
        "wineBottleVolume",
        "wineBottleAlcohol",
        "wineBottleSugarContent",
        "wineBottleYearName",
    )
    for row in stable_session_small_rows["result"]:
        for f in string_fields:
            v = row.get(f)
            # Null is tolerated; strings are the norm.
            assert v is None or isinstance(v, str), (
                f"{f} has unexpected type {type(v).__name__} in {row}"
            )


def test_M026_rating_points_is_a_float(stable_session_small_rows):
    """`wineBottleRatePoints` is a JSON number (float), not a string — the only numeric-encoded scalar on the row."""
    rows = stable_session_small_rows["result"]
    assert rows
    for row in rows:
        v = row.get("wineBottleRatePoints")
        assert isinstance(v, (int, float)), (
            f"wineBottleRatePoints has unexpected type {type(v).__name__}"
        )


def test_M027_external_link_shape(stable_session_small_rows):
    """`wineBottleExternalLink`, when present, is an object with exactly two keys — `text` and `link`. Both are strings."""
    for row in stable_session_small_rows["result"]:
        link = row.get("wineBottleExternalLink")
        if link is None:
            continue
        assert set(link.keys()) == {"text", "link"}, f"unexpected link shape: {link}"
        assert link["text"] is None or isinstance(link["text"], str)
        assert link["link"] is None or isinstance(link["link"], str)


def test_M028_external_link_text_is_usually_a_systembolaget_article_number(
    session, api_base
):
    """Across the full corpus, the overwhelming majority (≥80%) of non-empty `wineBottleExternalLink.text` values are digit-strings — the Systembolaget article number (either a 4–5 digit legacy form or a 6+ digit modern productNumber)."""
    body = post_list(session, api_base, pageIndex=0, pageSize=100000, sortOrder="")
    numeric = 0
    non_empty = 0
    for row in body["result"]:
        link = row.get("wineBottleExternalLink")
        if not link:
            continue
        t = link.get("text")
        if not t:
            continue
        non_empty += 1
        if t.isdigit():
            numeric += 1
    assert non_empty > 1000, "expected thousands of non-empty external-link texts"
    ratio = numeric / non_empty
    assert ratio >= 0.80, f"only {ratio:.0%} of link texts are digit strings"


def test_M029_external_link_text_includes_natvin_marker(session, api_base):
    """At least some rows use the sentinel `"Nätvin"` (online-only wine) as `wineBottleExternalLink.text` instead of an article number. Clients must treat this marker as "no article number" rather than parsing it as an id."""
    body = post_list(session, api_base, pageIndex=0, pageSize=100000, sortOrder="")
    natvin = 0
    for row in body["result"]:
        link = row.get("wineBottleExternalLink")
        if link and (link.get("text") or "").lower().startswith("nätvin"):
            natvin += 1
    assert natvin >= 100, f"expected many Nätvin markers in the corpus, saw {natvin}"


def test_M030_pageIndex_is_silently_ignored(session, api_base, stable_session_small):
    """`pageIndex` is silently ignored: changing it while holding other parameters fixed returns the same first-N rows. There is no true pagination; callers must use a large `pageSize` instead."""
    def fetch(page):
        return post_list(
            session,
            api_base,
            pageIndex=page,
            pageSize=5,
            sortOrder="",
            **{"wineBottleActivityName[]": [stable_session_small]},
        )

    r0 = fetch(0)
    r1 = fetch(1)
    r2 = fetch(7)
    names0 = [i["wineBottleName"] for i in r0["result"]]
    names1 = [i["wineBottleName"] for i in r1["result"]]
    names2 = [i["wineBottleName"] for i in r2["result"]]
    assert names0 == names1 == names2


def test_M031_pageSize_caps_result_length(session, api_base, stable_session_large):
    """`pageSize` sets the maximum number of rows returned. When `pageSize < total`, the response contains exactly `pageSize` rows; when `pageSize >= total`, it contains `total` rows. There is no observed upper cap on `pageSize`."""
    large = post_list(
        session,
        api_base,
        pageIndex=0,
        pageSize=1000,
        sortOrder="",
        **{"wineBottleActivityName[]": [stable_session_large]},
    )
    total = large["total"]
    assert total > 20  # sanity: this stable session has many rows
    assert len(large["result"]) == total

    small = post_list(
        session,
        api_base,
        pageIndex=0,
        pageSize=5,
        sortOrder="",
        **{"wineBottleActivityName[]": [stable_session_large]},
    )
    assert small["total"] == total
    assert len(small["result"]) == 5


def test_M032_pageSize_has_no_observed_upper_cap(session, api_base):
    """A very large `pageSize` (e.g. 100000) returns the entire unfiltered corpus in one response — `total` and `len(result)` match. The endpoint does not enforce a max page size, so callers can pull the whole dataset in a single request."""
    body = post_list(session, api_base, pageIndex=0, pageSize=100000, sortOrder="")
    assert body["total"] == len(body["result"])
    # Sanity: the corpus is the full historical archive, tens of thousands of rows.
    assert body["total"] >= 20000


def test_M033_activity_name_filter_restricts_results(
    session, api_base, stable_session_small
):
    """`wineBottleActivityName[]` is a real filter: every returned row has its `wineBottleActivityName` among the filter values — but the response field carries the *label only* (no `YYYYMMDD-` prefix), while the filter key carries the full `YYYYMMDD-<label>` form."""
    body = post_list(
        session,
        api_base,
        pageIndex=0,
        pageSize=1000,
        sortOrder="",
        **{"wineBottleActivityName[]": [stable_session_small]},
    )
    rows = body["result"]
    assert rows
    # The filter key prefixes the label with YYYYMMDD-; the row's activity name
    # carries only the label suffix after the dash.
    _, _, label = stable_session_small.partition("-")
    for row in rows:
        assert row["wineBottleActivityName"] == label, (
            f"expected activity label {label!r}, got {row['wineBottleActivityName']!r}"
        )


def test_M034_activity_name_filter_is_repeatable_and_ORs_values(
    session, api_base, stable_session_small
):
    """`wineBottleActivityName[]` is repeatable in one request; the server ORs the values and returns rows from any of the named sessions. `total` for the OR equals the sum of the per-session totals (the sessions are disjoint)."""
    key1 = stable_session_small
    key2 = "19980201-Beställningssortimentet 1998 02 Februari"

    def total_for(keys):
        body = post_list(
            session,
            api_base,
            pageIndex=0,
            pageSize=1000,
            sortOrder="",
            **{"wineBottleActivityName[]": keys},
        )
        return body["total"], body["result"]

    t1, _ = total_for([key1])
    t2, _ = total_for([key2])
    t_both, rows_both = total_for([key1, key2])
    assert t_both == t1 + t2

    label1 = key1.partition("-")[2]
    label2 = key2.partition("-")[2]
    labels = {r["wineBottleActivityName"] for r in rows_both}
    assert labels == {label1, label2}


def test_M035_unknown_session_key_returns_empty_result(session, api_base):
    """Filtering by a session key that does not exist yields `total == 0` and an empty `result` — no HTTP error."""
    body = post_list(
        session,
        api_base,
        pageIndex=0,
        pageSize=1000,
        sortOrder="",
        **{"wineBottleActivityName[]": ["bogus-session-key-does-not-exist"]},
    )
    assert body["total"] == 0
    assert body["result"] == []


def test_M036_non_empty_sortOrder_returns_500(session, api_base, stable_session_small):
    """`sortOrder` must be an empty string; any non-empty value (e.g. `"price"`, `"points"`) returns HTTP 500. There is no working client-side sort — callers must sort after fetching."""
    bad_values = ["price", "points", "year", "rating", "priceAsc"]
    for so in bad_values:
        resp = session.post(
            f"{api_base}{LIST_PATH}",
            data=[
                ("pageIndex", 0),
                ("pageSize", 3),
                ("sortOrder", so),
                ("wineBottleActivityName[]", stable_session_small),
            ],
            timeout=30,
        )
        assert resp.status_code == 500, (
            f"expected 500 for sortOrder={so!r}, got {resp.status_code}"
        )


def test_M037_unfiltered_query_duplicates_wines_across_sessions(session, api_base):
    """Without a `wineBottleActivityName[]` filter, a wine published to multiple sessions appears once per session it was published to. Row count exceeds the number of distinct (name, year) pairs — so the raw unfiltered `total` does not equal the number of unique tasting notes."""
    body = post_list(session, api_base, pageIndex=0, pageSize=100000, sortOrder="")
    rows = body["result"]
    distinct_wines = len({(r["wineBottleName"], r["wineBottleYearName"]) for r in rows})
    assert len(rows) > distinct_wines, (
        "expected row count to exceed distinct wine count (duplication across sessions)"
    )
    # A real but bounded duplication rate.
    dup_ratio = (len(rows) - distinct_wines) / len(rows)
    assert 0 < dup_ratio < 0.30, (
        f"duplication rate {dup_ratio:.2%} outside expected band (0, 30%)"
    )
