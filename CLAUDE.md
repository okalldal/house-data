# CLAUDE.md

Working notes for this project so we don't have to repeat ourselves.

## What this project is

House-sales research: scrape Booli's Open API for **past sales of homes in
Sweden** (`/sold`), to build a durable dataset of transaction prices for
analysis.

The methodology is deliberately copied from the sibling `wine-guide/` repo
(vendored here as a subtree): an `api-docs/` research subproject where **the
probe tests are the source of truth**, every documented claim is backed by a
live probe, and the downstream pipeline is built only on verified behaviour.
Read `api-docs/booli/STRATEGY.md` first.

## Two data paths

1. **Public site** (`www.booli.se`, no key) — the no-credentials route. A React
   app behind a Cloudflare managed challenge, so we drive a real browser
   (Playwright/Chromium) past the challenge and intercept the GraphQL responses
   it loads. **Requires a residential IP** — Cloudflare loops forever on
   datacenter/VPN/proxy IPs (verified; see `api-docs/booli/PUBLIC_SITE.md`).
   Implemented in `lib/booli_browser.py` + `scrape_public.py`.
2. **Open API** (`https://api.booli.se`, needs a key) — a credentialled REST API
   (Apache/PHP, **not** Cloudflare-gated). Fast and server-friendly. Authoritative
   for `booliId`, `soldPrice`, `soldDate`, object type, area, size, location.
   Implemented in `lib/booli_api.py` + `scrape_sold.py`.

Use the public path for data now without waiting for a key; use the Open API for
unattended/server-side runs once a key arrives.

## Credentials

The Open API gates data behind a `callerId` + private key, issued by Booli.
Request one from `api@booli.se` (the live API tells you so — claim B004), then:

```sh
export BOOLI_CALLER_ID=your-caller-id
export BOOLI_KEY=your-private-key
```

These are read from the environment by `lib/booli_api.py` and the probe suite.
Never commit them.

## Repo layout

- **`api-docs/booli/`** — the API research subproject. **Start here.**
  - `api.md` — verified reference. Endpoints, auth, response shapes. Each claim
    tagged `[B###]`. Claims marked **PENDING** need a key to verify.
  - `STRATEGY.md` — the "we probe, we do not test" research approach and the
    unauthenticated-vs-authenticated claim tiers.
  - `tests/` — pytest probes. `test_auth.py` runs with no key; `test_sold.py`
    needs credentials (`@requires_credentials`, auto-skips). `conftest.py`
    holds the auth signing and shared fixtures.
- **`lib/`** — shared library imported by the pipeline:
  - `lib/booli_browser.py` — `BooliBrowser`: Playwright scraper for the public
    site; clears Cloudflare, intercepts `/graphql` responses, extracts sales.
  - `lib/booli_api.py` — `BooliClient`: Open API auth signing, `get()`,
    `iter_sold()` pagination, `resolve_area()`.
  - `lib/cache.py` — atomic JSON writes, TTL helper, `cache/` + `data/` paths.
- **Pipeline scripts at the repo root:**
  - `scrape_public.py --url "<slutpriser-url>"` → `data/public_*.csv` — no key;
    drives a browser. Run from a residential IP.
  - `scrape_sold.py --area "<kommun>"` → `data/sold_<region>.csv` — Open API;
    needs `BOOLI_CALLER_ID`/`BOOLI_KEY`.
- **`data/`** — CSV artefacts (gitignored; regenerate with the pipeline).
- **`cache/`** — raw API pages (gitignored).
- **`wine-guide/`** — the reference project, vendored as a subtree. Source of
  the methodology; not run as part of this project.

## Verification workflow

Whenever you touch anything that relies on API behaviour:

```sh
pip install -r requirements.txt
pytest api-docs/booli/tests/ -m "not requires_credentials"   # always runnable
pytest api-docs/booli/tests/                                  # full, needs a key
```

If a probe fails, **our claim is wrong, not the API** — re-probe, fix the claim
and the test together, update `api.md`. Never loosen an assertion to get green.

## Claim status (snapshot)

- **Verified, no setup:** Open API auth contract + routing (`B001`–`B008`) and
  the public site being Cloudflare-gated (`B020`).
- **PENDING (need a key):** the `/sold` data shape, query params, pagination —
  `B010`–`B017`.
- **PENDING (need Playwright + a residential IP):** the public-site browser path
  clearing Cloudflare and yielding sales — `B021`. Run
  `pytest api-docs/booli/tests/test_public.py` from home to confirm, then drop
  its PENDING tag.
