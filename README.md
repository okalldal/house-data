# house-data

Scrape [Booli](https://www.booli.se) for data on **past sales of homes in
Sweden**, using the same probe-driven methodology as the sibling
[`wine-guide`](./wine-guide) project: an `api-docs/` research subproject where
the live API probes are the source of truth, and every documented claim is
backed by a test.

There are two ways to get the data. Pick based on whether you have an API key.

### A) Public site — no key, runs on your own machine

Drives a real browser past Cloudflare and harvests the sold listings the site
loads. **Must run from a residential IP** (Cloudflare blocks datacenter/VPN/proxy
IPs). See [`api-docs/booli/PUBLIC_SITE.md`](api-docs/booli/PUBLIC_SITE.md).

```sh
pip install -r requirements.txt
pip install playwright && playwright install chromium

python scrape_public.py --url "https://www.booli.se/slutpriser/nacka/76208/"
#   -> data/public_nacka_76208.csv   (use --headful the first time to watch it)
```

### B) Open API — needs a free key, but fast and server-friendly

```sh
pip install -r requirements.txt

# Auth/routing claims we can verify with no key at all:
pytest api-docs/booli/tests/ -m "not requires_credentials and not requires_browser"

# Get a Booli identity from api@booli.se, then verify the full data contract
# and scrape:
export BOOLI_CALLER_ID=your-caller-id BOOLI_KEY=your-private-key
pytest api-docs/booli/tests/
python scrape_sold.py --area "Nacka"        # -> data/sold_nacka.csv
```

## Layout

| Path                  | What it is                                                       |
| --------------------- | --------------------------------------------------------------- |
| `api-docs/booli/`     | **Start here.** Verified API reference (`api.md`), public-site notes (`PUBLIC_SITE.md`), strategy (`STRATEGY.md`), and live probes (`tests/`). |
| `lib/booli_browser.py`| Playwright scraper for the public site (Cloudflare + GraphQL interception). |
| `lib/booli_api.py`    | `BooliClient` — Open API auth signing, paginated `/sold` iteration. |
| `lib/cache.py`        | Atomic JSON cache helpers.                                       |
| `scrape_public.py`    | Public-site pipeline (no key): `--url` → `data/public_*.csv`.    |
| `scrape_sold.py`      | Open API pipeline (key): region → `data/sold_<region>.csv`.      |
| `wine-guide/`         | The reference project this methodology is copied from.          |
| `CLAUDE.md`           | Project working notes.                                           |

## Two paths, one trade-off

`www.booli.se` is behind a Cloudflare managed challenge, so the public path (A)
needs a real browser **and a residential IP** but no key. `api.booli.se` is
Booli's purpose-built Open API (Apache/PHP, no Cloudflare) — fast and
server-friendly, but it needs a credential pair from `api@booli.se`. Full
reasoning and the verified Cloudflare/TLS findings are in
`api-docs/booli/api.md` and `api-docs/booli/PUBLIC_SITE.md`.
