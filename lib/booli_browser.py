"""
Browser-based scraper for Booli's *public* site (no API key needed).

Why a browser at all? `www.booli.se` is a React app behind a Cloudflare
managed challenge. A plain HTTP client (`requests`) gets a JS-challenge page,
never data. A real browser executes the challenge, and — crucially — from a
*trusted (residential) IP* Cloudflare clears it automatically. From a
datacenter / VPN / proxy IP the challenge loops forever, so run this from your
own machine, not a cloud host. (See api-docs/booli/PUBLIC_SITE.md.)

Approach: we don't reverse-engineer Booli's GraphQL query. We let the site
issue its own queries and **intercept the GraphQL responses**, then defensively
pull sold-listing objects out of whatever JSON comes back. That keeps us robust
to schema churn — if Booli renames a wrapper field, we still find the listings.

Requires Playwright:

    pip install playwright
    playwright install chromium
"""

from __future__ import annotations

import time
from typing import Iterator
from urllib.parse import urlencode, urlsplit, urlunsplit, parse_qsl

# Marker fields that identify a "sold listing" object inside an arbitrary
# GraphQL response. An object is treated as a sale if it has an id plus at
# least one sold-price/date signal.
_ID_KEYS = ("booliId", "id")
_SOLD_SIGNALS = ("soldPrice", "soldDate", "soldSqmPrice", "soldPriceSource")

# Chromium launch args. PostQuantumKyber is disabled because Chrome's large
# post-quantum ClientHello breaks TLS-terminating MITM proxies; it is a no-op
# on a normal network. The rest are standard headless-in-container hygiene.
CHROMIUM_ARGS = [
    "--no-sandbox",
    "--disable-dev-shm-usage",
    "--disable-features=PostQuantumKyber",
]


def _looks_like_sale(obj) -> bool:
    if not isinstance(obj, dict):
        return False
    has_id = any(k in obj for k in _ID_KEYS)
    has_sold = any(k in obj for k in _SOLD_SIGNALS)
    return has_id and has_sold


def _walk_for_sales(node, out: list) -> None:
    """Recursively collect every dict in `node` that looks like a sold listing."""
    if isinstance(node, dict):
        if _looks_like_sale(node):
            out.append(node)
        for v in node.values():
            _walk_for_sales(v, out)
    elif isinstance(node, list):
        for v in node:
            _walk_for_sales(v, out)


def extract_sales(graphql_json) -> list[dict]:
    """Pull sold-listing dicts out of one intercepted GraphQL response body."""
    out: list[dict] = []
    _walk_for_sales(graphql_json, out)
    return out


def _with_page(url: str, page_num: int) -> str:
    """Return `url` with its `page` query param set to `page_num`."""
    parts = urlsplit(url)
    q = dict(parse_qsl(parts.query))
    q["page"] = str(page_num)
    return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(q), parts.fragment))


class BooliBrowser:
    """Drive a real Chromium past Cloudflare and harvest sold listings.

    Usage:
        with BooliBrowser() as b:
            for sale in b.iter_sold_url("https://www.booli.se/slutpriser/nacka/76208/"):
                ...
    """

    def __init__(self, *, headless: bool = True, proxy: str | None = None,
                 challenge_timeout: float = 60.0, nav_timeout: float = 90.0):
        self.headless = headless
        self.proxy = proxy
        self.challenge_timeout = challenge_timeout
        self.nav_timeout = nav_timeout * 1000
        self._pw = None
        self._browser = None
        self._ctx = None

    def __enter__(self):
        from playwright.sync_api import sync_playwright

        self._pw = sync_playwright().start()
        launch_kwargs = {"headless": self.headless, "args": CHROMIUM_ARGS}
        if self.proxy:
            launch_kwargs["proxy"] = {"server": self.proxy}
        self._browser = self._pw.chromium.launch(**launch_kwargs)
        self._ctx = self._browser.new_context(
            locale="sv-SE",
            user_agent=("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                        "(KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36"),
        )
        return self

    def __exit__(self, *exc):
        for closer in (self._ctx, self._browser):
            try:
                if closer:
                    closer.close()
            except Exception:
                pass
        if self._pw:
            self._pw.stop()

    def _wait_for_clearance(self, page) -> bool:
        """Block until Cloudflare clears (cf_clearance cookie appears) or timeout.

        Returns True if cleared. A persistent challenge almost always means the
        current IP is distrusted — run from a residential connection.
        """
        deadline = time.time() + self.challenge_timeout
        while time.time() < deadline:
            names = {c["name"] for c in self._ctx.cookies()}
            title = (page.title() or "")
            challenging = ("Vänta" in title or "Just a moment" in title)
            if "cf_clearance" in names and not challenging:
                return True
            page.wait_for_timeout(1500)
        return "cf_clearance" in {c["name"] for c in self._ctx.cookies()}

    def fetch_sold_page(self, url: str) -> list[dict]:
        """Navigate one slutpriser URL and return the sales harvested from it."""
        page = self._ctx.new_page()
        captured: list[dict] = []

        def on_response(resp):
            try:
                if resp.url.endswith("/graphql") and resp.request.method == "POST":
                    captured.append(resp.json())
            except Exception:
                pass

        page.on("response", on_response)
        try:
            page.goto(url, timeout=self.nav_timeout, wait_until="domcontentloaded")
            cleared = self._wait_for_clearance(page)
            if not cleared:
                raise CloudflareBlocked(
                    "Cloudflare did not clear — the current IP is likely "
                    "distrusted. Run from a residential connection.")
            # Let the page's GraphQL calls fire and settle.
            try:
                page.wait_for_load_state("networkidle", timeout=15000)
            except Exception:
                pass
            page.wait_for_timeout(1500)
        finally:
            sales: list[dict] = []
            for body in captured:
                sales.extend(extract_sales(body))
            page.close()
        return sales

    def iter_sold_url(self, url: str, *, max_pages: int = 200) -> Iterator[dict]:
        """Page through a slutpriser URL, yielding deduped sold listings.

        Stops when a page yields no new listings or `max_pages` is reached.
        """
        seen: set = set()
        for page_num in range(1, max_pages + 1):
            page_url = _with_page(url, page_num)
            sales = self.fetch_sold_page(page_url)
            new = 0
            for sale in sales:
                key = sale.get("booliId") or sale.get("id")
                if key in seen:
                    continue
                seen.add(key)
                new += 1
                yield sale
            if new == 0:
                break


class CloudflareBlocked(RuntimeError):
    """Raised when the Cloudflare challenge never clears (usually an IP problem)."""
