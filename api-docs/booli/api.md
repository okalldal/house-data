# Booli Open API — Verified Reference

Every **verified** claim on this page is backed by at least one probe in
`api-docs/booli/tests/`. Claim tags like `[B001]` map to test functions named
`test_B001_...`. See `STRATEGY.md` (alongside this file) for the research
approach, and run

```sh
pytest api-docs/booli/tests/ -m "not requires_credentials"   # no key needed
pytest api-docs/booli/tests/                                  # all, needs a key
```

from the repo root to re-verify this document against the live API.

- **Base URL:** `https://api.booli.se`
- **Backend:** Apache / PHP. **No Cloudflare** — plain HTTP clients work
  (unlike the consumer site, see "GraphQL alternative" below).
- **Auth:** every data request needs four params — `callerId`, `unique`,
  `time`, `hash` `[B002]`. Request a `callerId` + private key from
  `api@booli.se` `[B004]`.

Claims tagged **PENDING** describe the *data* and require a real identity to
verify. They are grounded on Booli's published Open API schema but are **not
yet confirmed** from this repo — their probes skip until `BOOLI_CALLER_ID` /
`BOOLI_KEY` are set. Do not rely on a PENDING claim as fact.

---

## Authentication

Every request to a data endpoint must carry four query parameters `[B002]`:

| Param      | Meaning                                                        |
| ---------- | ------------------------------------------------------------- |
| `callerId` | your issued identity                                          |
| `time`     | current unix timestamp, in seconds                            |
| `unique`   | a per-request nonce (any unguessable string)                  |
| `hash`     | `sha1(callerId + time + unique + key)`, hex digest **(PENDING B010)** |

The exact hash construction is implemented in
`api-docs/booli/tests/conftest.py::auth_params` and in `lib/booli_api.py`. It
cannot be confirmed without credentials — an unknown identity is rejected
*before* the hash is checked `[B004]` — so it is tracked as PENDING `B010`.

### Auth failure modes (verified, no key needed)

- A request **missing** any of the four params returns **HTTP 403** with a
  plain-text body beginning `FAILURE_MISSING_PARAM` `[B001]`. The body names
  all four required params `[B002]`. This holds for GET and POST alike
  `[B008]`.
- A request with **all four params present but an unrecognised `callerId`**
  returns **HTTP 403** beginning `FAILURE_IDENTITY_NOT_FOUND`, with the text
  *"Please contact api@booli.se to receive an identity."* `[B004]`.
- **Error bodies are plain text, not JSON** — of the shape
  `ERRORCODE - human message` — even though GET error responses carry an
  `application/json` content-type `[B005]`. Callers must not blindly
  `response.json()` an error.

---

## Endpoints

The host routes at least these data endpoints; each answers the auth error
(403) rather than a 404, confirming it exists `[B006]`:

| Endpoint      | Purpose                                              |
| ------------- | ---------------------------------------------------- |
| `/sold`       | **past sales** of homes — the focus of this project  |
| `/listings`   | currently-for-sale listings                          |
| `/areas`      | resolve area names / ids for use as search regions   |
| `/residences` | residence (address-level) records                    |

An unknown path returns **HTTP 404** `[B007]`, so 403-vs-404 cleanly
distinguishes "valid endpoint, not authenticated" from "no such endpoint".

---

## `GET /sold` — past home sales  *(data shape PENDING)*

The sales endpoint. Restrict results with a region plus optional filters, then
page through with `limit`/`offset`.

### Region selection

Pass exactly one region selector (grounded on Booli's published schema —
**PENDING**, verify once credentialled):

- `areaId=<id>` — an area id from `/areas` (a kommun, stadsdel, etc.).
- `q=<name>` — a free-text place name (e.g. `q=Nacka`).
- `center=<lat,lng>&dim=<w,h>` — a bounding box around a point.
- `bbox=<lat1,lng1,lat2,lng2>` — an explicit bounding box.

### Common filters *(PENDING)*

`minSoldDate`, `maxSoldDate` (ISO dates), `minSoldPrice`, `maxSoldPrice`,
`minRooms`, `maxRooms`, `minLivingArea`, `maxLivingArea`, `objectType`
(e.g. `Lägenhet`, `Villa`, `Radhus`).

### Response shape *(PENDING)*

- A JSON object with integer `totalCount`, integer `count`, and a `sold`
  array `[B011 PENDING]`.
- Each item exposes `booliId`, `soldPrice`, `soldDate`, `objectType`
  `[B012 PENDING]`.
- `soldPrice` is a positive number in SEK `[B013 PENDING]`; `soldDate` is an
  ISO `YYYY-MM-DD` string `[B014 PENDING]`.
- Each item carries a `location` object with a `position` (numeric
  `latitude` / `longitude`) `[B015 PENDING]`, plus address/region sub-objects.

### Pagination *(PENDING)*

- `limit` caps page size `[B016 PENDING]`; the API's own default/max page size
  is to be confirmed.
- `offset` pages through the full result set `[B017 PENDING]`.
- `totalCount` reports the full match count regardless of the current page —
  the basis for iterating every sale in a region.

---

## Public-site path (no key) — see `PUBLIC_SITE.md`

The consumer site `www.booli.se` renders sold listings from a GraphQL endpoint
at `www.booli.se/graphql`, and anyone can browse them without credentials — so
it is the **no-API-key** route. The catch: it **sits behind a Cloudflare managed
challenge**. A plain `requests`/`curl` GET is answered with an **HTTP 403**
JavaScript-challenge page (header `cf-mitigated: challenge`), never data
`[B020]`. Scraping it therefore requires:

- a **real browser** (Playwright + Chromium) to execute the challenge and the
  page's client-side GraphQL, and
- a **residential IP** — Cloudflare's managed challenge clears automatically for
  ordinary IPs but loops forever for datacenter/VPN/proxy IPs `[B021, PENDING —
  verify from a trusted IP]`.

This path is implemented in `lib/booli_browser.py` + `scrape_public.py` (it
intercepts the site's own GraphQL responses rather than reverse-engineering the
query). Full constraints, the post-quantum-TLS quirk, and verification steps are
in **`PUBLIC_SITE.md`**. Use it for data now without a key; use the Open API
above for fast, unattended, server-side runs once a key arrives.
