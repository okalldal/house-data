"""
Shared fixtures for Booli Open API probes.

Every fixture here makes live HTTP requests to https://api.booli.se.

Two tiers of probe live in this suite (see STRATEGY.md):

  * Unauthenticated probes need no setup — they observe routing and the auth
    contract. They run anywhere.
  * Authenticated probes observe the *data* and need a real Booli identity.
    They are decorated with ``@requires_credentials`` and skip cleanly unless
    BOOLI_CALLER_ID and BOOLI_KEY are set in the environment. Request one from
    api@booli.se (the live API tells you so — see claim B004).
"""

import hashlib
import os
import secrets
import time

import pytest
import requests

API_BASE = "https://api.booli.se"

CALLER_ID = os.environ.get("BOOLI_CALLER_ID")
KEY = os.environ.get("BOOLI_KEY")

HAVE_CREDENTIALS = bool(CALLER_ID and KEY)

def requires_credentials(func):
    """Mark a probe as authenticated: tag it (so ``-m "not requires_credentials"``
    deselects it) and skip it when no Booli identity is configured."""
    func = pytest.mark.requires_credentials(func)
    func = pytest.mark.skipif(
        not HAVE_CREDENTIALS,
        reason="set BOOLI_CALLER_ID and BOOLI_KEY to run authenticated data probes",
    )(func)
    return func

DEFAULT_HEADERS = {
    "Accept": "application/json",
    "User-Agent": "house-data-api-probe/1.0",
}


def _have_playwright():
    try:
        import playwright.sync_api  # noqa: F401
        return True
    except Exception:
        return False


def requires_browser(func):
    """Mark a probe as needing Playwright + a browser-clearable IP.

    Tags it (so ``-m "not requires_browser"`` deselects it) and skips it when
    Playwright is not installed. Probes that get past that but hit a persistent
    Cloudflare challenge should ``pytest.skip`` on CloudflareBlocked — a stuck
    challenge means the current IP is distrusted, not that a claim is false.
    """
    func = pytest.mark.requires_browser(func)
    func = pytest.mark.skipif(
        not _have_playwright(),
        reason="pip install playwright && playwright install chromium to run "
               "public-site probes (and run from a residential IP)",
    )(func)
    return func


def auth_params(caller_id=None, key=None):
    """Build the four Booli auth query params for the current instant.

    hash = sha1(callerId + time + unique + key), hex digest. ``time`` is a
    unix timestamp (seconds); ``unique`` is a per-request nonce. This exact
    construction is itself a claim (B010), verifiable only with real
    credentials — an unknown identity is rejected before the hash is checked.
    """
    caller_id = caller_id or CALLER_ID
    key = key or KEY
    unique = secrets.token_hex(8)
    ts = str(int(time.time()))
    digest = hashlib.sha1(
        (str(caller_id) + ts + unique + str(key)).encode("utf-8")
    ).hexdigest()
    return {"callerId": caller_id, "time": ts, "unique": unique, "hash": digest}


@pytest.fixture(scope="session")
def api_base():
    return API_BASE


@pytest.fixture(scope="session")
def session():
    s = requests.Session()
    s.headers.update(DEFAULT_HEADERS)
    return s


@pytest.fixture(scope="session")
def signed(session, api_base):
    """Return a function that performs an authenticated GET against an endpoint.

    Usage: ``resp = signed("sold", area="Nacka", maxSoldPrice=5000000)``
    Skips the calling test if no credentials are configured.
    """
    if not HAVE_CREDENTIALS:
        pytest.skip("no Booli credentials configured")

    def _get(endpoint, **params):
        params = {**params, **auth_params()}
        resp = session.get(f"{api_base}/{endpoint}", params=params, timeout=30)
        return resp

    return _get


@pytest.fixture(scope="session")
def sold_page(signed):
    """One page of sold homes for a large, stable kommun — shared structural sample.

    Nacka kommun (areaId 76208) is large enough to always return results and
    stable enough not to be renumbered. If this id ever 404s, pick another
    kommun via the /areas endpoint and update here.
    """
    resp = signed("sold", areaId=76208, limit=50)
    resp.raise_for_status()
    return resp.json()
