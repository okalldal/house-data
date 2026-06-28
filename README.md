# house-data

Scrape [Booli](https://www.booli.se) for data on **past sales of homes in
Sweden**, using the same probe-driven methodology as the sibling
[`wine-guide`](./wine-guide) project: an `api-docs/` research subproject where
the live API probes are the source of truth, and every documented claim is
backed by a test.

## Quick start

```sh
pip install -r requirements.txt

# 1. Verify the API contract we can check without a key (auth + routing):
pytest api-docs/booli/tests/ -m "not requires_credentials"

# 2. Get a Booli identity (callerId + key) from api@booli.se, then:
export BOOLI_CALLER_ID=your-caller-id
export BOOLI_KEY=your-private-key

# 3. Verify the full data contract against the live API:
pytest api-docs/booli/tests/

# 4. Scrape past sales for a region to CSV:
python scrape_sold.py --area "Nacka"
#   -> data/sold_nacka.csv
```

## Layout

| Path                  | What it is                                                       |
| --------------------- | --------------------------------------------------------------- |
| `api-docs/booli/`     | **Start here.** Verified API reference (`api.md`), research strategy (`STRATEGY.md`), and live probes (`tests/`). |
| `lib/booli_api.py`    | `BooliClient` — auth signing, paginated `/sold` iteration.       |
| `lib/cache.py`        | Atomic JSON cache helpers.                                       |
| `scrape_sold.py`      | Pipeline entry point: region → `data/sold_<region>.csv`.        |
| `wine-guide/`         | The reference project this methodology is copied from.          |
| `CLAUDE.md`           | Project working notes.                                           |

## Why `api.booli.se` and not the website

`www.booli.se` is behind a Cloudflare managed challenge, so a plain HTTP client
gets a JS-challenge page instead of data. `api.booli.se` is Booli's purpose-built
Open API (Apache/PHP, no Cloudflare) and returns clean JSON — at the cost of
requiring a credential pair. See `api-docs/booli/api.md` for the full reasoning.
