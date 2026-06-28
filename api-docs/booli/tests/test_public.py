"""
Probes for the PUBLIC site (www.booli.se) scraping path — no API key.

Two tiers:
  * B020 needs nothing but a network connection — it confirms Cloudflare gates
    the site (so a plain HTTP client cannot scrape it).
  * B021+ are @requires_browser: they drive a real Chromium past Cloudflare and
    need both Playwright installed AND a residential IP. They skip when
    Playwright is missing, and skip (not fail) when the IP is distrusted and the
    challenge never clears — a stuck challenge is an environment fact, not a
    false claim.

See PUBLIC_SITE.md for the full reasoning.
"""

import pytest
import requests

from conftest import requires_browser

# A large, stable kommun slutpriser URL. If this 404s, pick another from the
# site and update here.
SOLD_URL = "https://www.booli.se/slutpriser/nacka/76208/"


def test_B020_public_site_is_cloudflare_gated(session):
    """A plain HTTP GET of www.booli.se is answered with an HTTP 403 Cloudflare challenge (cf-mitigated: challenge), so the public site cannot be scraped without a JS-executing browser."""
    resp = requests.get("https://www.booli.se/", timeout=25,
                        headers={"User-Agent": "house-data-probe/1.0"})
    assert resp.status_code == 403
    assert resp.headers.get("cf-mitigated") == "challenge"
    assert "cloudflare" in resp.headers.get("server", "").lower()


@requires_browser
def test_B021_browser_clears_cloudflare_and_finds_sales():
    """From a trusted IP, a real Chromium clears Cloudflare on a slutpriser page and the intercepted GraphQL yields at least one sold listing carrying a booliId and a sold price."""
    import sys
    from pathlib import Path

    sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
    from lib.booli_browser import BooliBrowser, CloudflareBlocked

    try:
        with BooliBrowser(headless=True) as browser:
            sales = browser.fetch_sold_page(SOLD_URL)
    except CloudflareBlocked as e:
        pytest.skip(f"Cloudflare did not clear (distrusted IP?): {e}")

    assert sales, "no sold listings harvested from the page"
    sample = sales[0]
    assert sample.get("booliId") or sample.get("id")
    assert any(k in sample for k in ("soldPrice", "soldDate", "soldSqmPrice"))
