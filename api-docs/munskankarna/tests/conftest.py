"""
Shared fixtures for Munskänkarna API probes.

Every fixture here makes live HTTP requests to
`www.munskankarna.se/umbraco/surface/winesearch/`. No API key is
required; we send a polite `User-Agent` identifying the scraper.
"""

import pytest
import requests

API_BASE = "https://www.munskankarna.se"
LIST_PATH = "/umbraco/surface/winesearch/listwinebottles/"
FACETS_PATH = "/umbraco/surface/winesearch/getfacets/"

DEFAULT_HEADERS = {
    "User-Agent": "wine-guide-api-probe/1.0 (Munskänkarna research; polite)",
    "Accept": "application/json",
}

# A session old enough to be closed (no new tasting notes will land). Used
# when a probe needs to name a specific session; keeps the assertions stable
# as the public dataset grows.
STABLE_SESSION_SMALL = "19980101-Beställningssortimentet 1998 01 Januari"
STABLE_SESSION_LARGE = "20091101-Beställningssortimentet 2009 11 November"


@pytest.fixture(scope="session")
def api_base():
    return API_BASE


@pytest.fixture(scope="session")
def session():
    s = requests.Session()
    s.headers.update(DEFAULT_HEADERS)
    return s


@pytest.fixture(scope="session")
def stable_session_small():
    """A session key old enough that its tasting-note list is frozen."""
    return STABLE_SESSION_SMALL


@pytest.fixture(scope="session")
def stable_session_large():
    """A stable session key with ~80 tasting notes — enough to probe pagination edges."""
    return STABLE_SESSION_LARGE


@pytest.fixture(scope="session")
def facets_response(session, api_base):
    """The full `getfacets` response body, fetched once per test session."""
    resp = session.get(f"{api_base}{FACETS_PATH}", timeout=30)
    resp.raise_for_status()
    return resp.json()


@pytest.fixture(scope="session")
def stable_session_small_rows(session, api_base, stable_session_small):
    """All rows returned for the small stable session, in a single call."""
    params = [
        ("pageIndex", 0),
        ("pageSize", 1000),
        ("sortOrder", ""),
        ("wineBottleActivityName[]", stable_session_small),
    ]
    resp = session.post(f"{api_base}{LIST_PATH}", data=params, timeout=60)
    resp.raise_for_status()
    return resp.json()


def post_list(session, api_base, **params):
    """Issue a POST to listwinebottles. `params` is a flat dict; list values are unpacked."""
    body = []
    for k, v in params.items():
        if isinstance(v, (list, tuple)):
            for item in v:
                body.append((k, item))
        else:
            body.append((k, v))
    resp = session.post(f"{api_base}{LIST_PATH}", data=body, timeout=60)
    resp.raise_for_status()
    return resp.json()
