# Booli public site (`www.booli.se`) — scraping notes

The no-API-key path. The consumer site renders sold listings ("slutpriser")
that anyone can browse without credentials, so we can scrape them — but it is a
React app behind Cloudflare, which changes what "scrape" means. This file
records what we verified about that path and what it requires.

## What you need

1. **A real browser** (Playwright + Chromium). The site ships almost no data in
   the initial HTML; it loads listings client-side via GraphQL, and Cloudflare
   gates the page with a JavaScript challenge. `requests`/`curl` cannot execute
   either, so they only ever see the challenge page — **verified**: a plain
   `GET https://www.booli.se/` returns **HTTP 403** with a Cloudflare
   `cf-mitigated: challenge` header and a "Vänta…" interstitial, never listings.

2. **A trusted (residential) IP.** Cloudflare's *managed challenge* clears
   automatically for ordinary home/office IPs but **loops indefinitely for
   datacenter / VPN / cloud / proxy IPs** — **verified**: from this project's
   cloud egress IP, a headful Chromium ran the Turnstile challenge to
   completion's resources (challenges.cloudflare.com returned 200s) yet **never
   received a `cf_clearance` cookie** after 55 s; only the pre-clearance
   `__cf_bm` cookie was set. The same browser on a residential line clears in a
   few seconds. **This is the single hard requirement** — run the scraper from
   your own machine, not a server.

3. **(Behind a TLS-terminating proxy only) disable Chrome's post-quantum
   ClientHello.** **Verified**: Chrome ≥ 124 sends an X25519MLKEM768 key share
   that makes a large ClientHello some MITM proxies cannot parse, causing
   `ERR_CONNECTION_CLOSED` mid-handshake. Launch flag
   `--disable-features=PostQuantumKyber` fixes it. This is irrelevant on a
   normal home network (no MITM) but harmless to leave on. `lib/booli_browser.py`
   sets it by default.

## How we harvest the data

We do **not** reverse-engineer Booli's GraphQL query (it uses persisted/POST
queries that change). Instead `lib/booli_browser.py`:

1. launches Chromium and navigates the `slutpriser` URL you give it;
2. waits for `cf_clearance` to appear (Cloudflare cleared);
3. **intercepts every `POST …/graphql` response** the page makes;
4. walks the response JSON and pulls out any object that looks like a sale —
   has an id (`booliId`/`id`) plus a sold signal (`soldPrice`/`soldDate`/…).

This response-interception design is resilient to wrapper-field renames: as long
as the site shows you sold prices, we can scrape them.

## URL shape

The sold-listings pages follow `https://www.booli.se/slutpriser/<area>/<areaId>/`
(e.g. `/slutpriser/nacka/76208/`) and accept a `?page=N` query param for
pagination. Pass the exact URL you browse to `scrape_public.py --url`; we add
`?page=N` and stop when a page yields no new listings. **Verified** only as far
as the routing (a `/slutpriser/...` path 307-redirects then serves the
Cloudflare challenge, i.e. it is a real route); the page-param pagination and
the response field names are **PENDING** until confirmed from a residential IP
with `tests/test_public.py`.

## Verifying on your machine

```sh
pip install playwright && playwright install chromium
pytest api-docs/booli/tests/test_public.py -v     # needs a residential IP + browser
python scrape_public.py --url "https://www.booli.se/slutpriser/nacka/76208/" --headful
```

If the probe raises `CloudflareBlocked`, your IP is distrusted — try a
different (home) network. Run `--headful` once to watch the challenge clear.

## Trade-off vs. the Open API

| | Public site (this file) | Open API (`api.md`) |
| --- | --- | --- |
| Credentials | none | `callerId` + key from api@booli.se |
| Tooling | Playwright + Chromium | `requests` only |
| Runs on a server | no (IP must be residential) | yes |
| Fragility | higher (Cloudflare, DOM/GraphQL churn) | lower (stable REST contract) |
| Speed | slow (a browser per page) | fast |

Use the public path when you want data now without waiting for a key; switch to
the Open API for unattended/server-side runs once a key arrives.
