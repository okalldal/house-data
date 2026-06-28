"""
Probes for invariants that span both endpoints.

Each test's first docstring line is the claim it establishes.
"""

import re

from conftest import post_list


def _parse_paren_count(label):
    """`"(17)"` → `17`."""
    m = re.search(r"\((\d+)\)", label or "")
    return int(m.group(1)) if m else None


def test_M040_activity_facet_count_matches_listwinebottles_total(
    session, api_base, facets_response, stable_session_small
):
    """The `(N)` count inside `facets.wineBottleActivityName[*].item3` for a given session equals `listwinebottles.total` when filtering by that session's `item2` key. Facet counts are consistent with listing results."""
    match = next(
        a for a in facets_response["facets"]["wineBottleActivityName"]
        if a["item2"] == stable_session_small
    )
    facet_count = _parse_paren_count(match["item3"])
    assert facet_count is not None, f"could not parse item3: {match['item3']!r}"

    body = post_list(
        session,
        api_base,
        pageIndex=0,
        pageSize=1000,
        sortOrder="",
        **{"wineBottleActivityName[]": [stable_session_small]},
    )
    assert body["total"] == facet_count


def test_M041_sum_of_activity_facet_counts_equals_unfiltered_total(
    session, api_base, facets_response
):
    """The sum of the parenthesised counts across every `wineBottleActivityName` facet entry equals the unfiltered `listwinebottles.total`. This confirms the unfiltered listing is the union of sessions — each row appears once per session it was published to — and quantifies how much duplication the unfiltered query introduces."""
    total_from_facets = sum(
        _parse_paren_count(a["item3"]) or 0
        for a in facets_response["facets"]["wineBottleActivityName"]
    )
    body = post_list(session, api_base, pageIndex=0, pageSize=1, sortOrder="")
    assert body["total"] == total_from_facets


def test_M042_activity_facet_item2_is_accepted_by_list_filter(
    session, api_base, facets_response
):
    """Every `facets.wineBottleActivityName[*].item2` value round-trips as a valid `wineBottleActivityName[]` filter value on `listwinebottles/` — i.e. the two endpoints share a namespace for session keys."""
    # Sample a handful from across the list to keep the probe fast.
    activities = facets_response["facets"]["wineBottleActivityName"]
    sampled = activities[:3] + activities[len(activities) // 2 : len(activities) // 2 + 3] + activities[-3:]
    for a in sampled:
        body = post_list(
            session,
            api_base,
            pageIndex=0,
            pageSize=1,
            sortOrder="",
            **{"wineBottleActivityName[]": [a["item2"]]},
        )
        expected = _parse_paren_count(a["item3"])
        assert body["total"] == expected, (
            f"session {a['item2']!r}: facet count {expected}, list total {body['total']}"
        )
