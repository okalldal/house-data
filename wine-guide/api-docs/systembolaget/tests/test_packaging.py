"""
Probes for product-number structure as it relates to bottle size and
packaging variants.

Packaging variants ("siblings") share the first N-2 characters of the
`productNumber` and differ in the last two. The catalog exposes the
grouping (same `productNameBold` across siblings — see C012); the search
endpoint exposes the differentiating attributes (`volume`,
`packagingLevel1`, price, etc.).

These probes fetch a bounded corpus from a single country partition
(Italy, 10 pages) so they do not depend on a fixed productNumber staying
in the catalog.

Each test's first docstring line is the claim it establishes.
"""

from collections import defaultdict


def _sibling_groups(products):
    """Group products by productNumber[:-2]; return groups with >1 member."""
    groups = defaultdict(list)
    for p in products:
        groups[p["productNumber"][:-2]].append(p)
    return [g for g in groups.values() if len(g) > 1]


def test_C013_siblings_can_differ_in_volume(italy_wine_sample):
    """Within at least one wine sibling group (productNumber prefix shared), the members carry different `volume` values — confirming the last two productNumber characters encode bottle size, not just a sequence number. A caller that wants "the 750 ml version" of a wine must select a specific sibling, not treat any member as interchangeable."""
    groups = _sibling_groups(italy_wine_sample)
    assert groups, "no sibling groups in the sample; expand the fixture"

    for group in groups:
        volumes = {p.get("volume") for p in group}
        if len(volumes) > 1:
            # Confirmed. Name survives as diagnostic if the test later regresses.
            names = {p.get("productNameBold") for p in group}
            assert names, f"volume-varied group has no names: {group}"
            return

    raise AssertionError(
        "no sibling group with differing volume found — either the sample is "
        "too narrow or the claim is wrong"
    )


def test_C014_siblings_can_differ_in_packagingLevel1(italy_wine_sample):
    """Within at least one wine sibling group, the members carry different `packagingLevel1` values (e.g. "Glasflaska" vs "Bag-in-Box") — the last two productNumber characters can encode a packaging-type variant, not only a size variant."""
    groups = _sibling_groups(italy_wine_sample)
    assert groups, "no sibling groups in the sample; expand the fixture"

    for group in groups:
        packagings = {p.get("packagingLevel1") for p in group}
        if len(packagings) > 1:
            return

    raise AssertionError(
        "no sibling group with differing packagingLevel1 found — either the "
        "sample is too narrow or the claim is wrong"
    )


def test_C015_siblings_usually_share_productName_in_search(italy_wine_sample):
    """Sibling wines observed via the search endpoint also usually share a single `productNameBold`, consistent with the same heuristic seen in the catalog (see C012). At least 80% of multi-member sibling groups in the search-derived sample share a name — the search endpoint does not contradict the catalog's view of which productNumbers belong to the "same" wine."""
    groups = _sibling_groups(italy_wine_sample)
    assert groups, "no sibling groups in the sample; widen the fixture"

    same_name = sum(1 for g in groups
                    if len({p.get("productNameBold") for p in g}) == 1)
    ratio = same_name / len(groups)
    assert ratio >= 0.80, (
        f"only {same_name}/{len(groups)} sibling groups share a name in the "
        f"search sample (ratio={ratio:.2f})"
    )
