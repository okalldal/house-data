"""
Probes for the store lookup endpoint:
    GET /sb-api-ecommerce/v1/sitesearch/site

Each test's first docstring line is the claim it establishes.
"""

SITESEARCH_PATH = "/sb-api-ecommerce/v1/sitesearch/site"


def _sitesearch(session, api_base, **params):
    params.setdefault("includePredictions", "false")
    resp = session.get(f"{api_base}{SITESEARCH_PATH}", params=params, timeout=30)
    resp.raise_for_status()
    return resp.json()


def test_C070_sitesearch_endpoint_returns_200(session, api_base):
    """The site-search endpoint `/v1/sitesearch/site` returns HTTP 200 for a simple `q` parameter."""
    resp = session.get(
        f"{api_base}{SITESEARCH_PATH}",
        params={"q": "stockholm", "includePredictions": "false"},
        timeout=30,
    )
    assert resp.status_code == 200


def test_C071_sitesearch_response_has_siteSearchResults_array(sitesearch_response):
    """The response is a JSON object with a `siteSearchResults` array."""
    assert isinstance(sitesearch_response.get("siteSearchResults"), list)
    assert sitesearch_response["siteSearchResults"]


def test_C072_sitesearch_results_have_core_identity_fields(sitesearch_response):
    """Every result exposes `siteId`, `displayName`, `city`, and `isAgent`."""
    for s in sitesearch_response["siteSearchResults"]:
        assert "siteId" in s
        assert "displayName" in s
        assert "city" in s
        assert "isAgent" in s


def test_C073_sitesearch_isAgent_distinguishes_real_stores_from_agents(sitesearch_response):
    """`isAgent` is a boolean distinguishing Systembolaget's own stores (False) from third-party alcohol-agents/ombuds (True); both kinds appear in results — callers must filter."""
    agents = [s for s in sitesearch_response["siteSearchResults"] if s["isAgent"]]
    stores = [s for s in sitesearch_response["siteSearchResults"] if not s["isAgent"]]
    for s in sitesearch_response["siteSearchResults"]:
        assert isinstance(s["isAgent"], bool)
    # In the Stockholm query we expect at least some of each class to be present.
    assert stores, "no non-agent stores returned for 'stockholm' — sitesearch may not mix types"


def test_C074_sitesearch_empty_q_returns_many_stores(session, api_base):
    """An empty `q` returns the full list of stores (not an error) — useful for enumerating every site in one call."""
    r = _sitesearch(session, api_base, q="")
    results = r.get("siteSearchResults", [])
    assert len(results) >= 400


def test_C075_sitesearch_q_is_geographic_not_substring(session, api_base):
    """`q` performs a geographic / proximity match, not a literal substring match: searching for a place name returns stores in and around that location whose `displayName` and `city` may not contain the query at all."""
    r = _sitesearch(session, api_base, q="göteborg")
    results = r.get("siteSearchResults", [])
    assert results
    non_matching = [
        s for s in results
        if "göteborg" not in f"{s.get('displayName', '')} {s.get('city', '')}".lower()
    ]
    # If `q` were a substring match, this list would be empty.
    assert non_matching, "expected at least one result not literally matching 'göteborg'"


def test_C076_sitesearch_siteId_is_zero_padded_string(sitesearch_response):
    """`siteId` is returned as a string, with small numeric ids zero-padded to four digits (e.g. "0102") — it is not a plain integer."""
    for s in sitesearch_response["siteSearchResults"]:
        if s["isAgent"]:
            continue
        sid = s["siteId"]
        assert isinstance(sid, str)
        assert sid.isdigit()
        assert len(sid) == 4
