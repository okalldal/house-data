# Booli API — Research Strategy

## Purpose

We are building durable knowledge of Booli's `api.booli.se` Open API, so that
future applications can be built on top of it confidently. The output of this
project is a body of *verified* facts about how the API behaves, with a
particular focus on **past sales of homes in Sweden** (the `/sold` endpoint).

## Core principle: we probe, we do not test

We do not own this API. We cannot assert what it *should* do — only observe
what it *does* do. Our pytest suite is a set of probes, not traditional tests:

- If a probe passes, our documented claim is confirmed.
- If a probe fails, **our claim is wrong, not the API**. The correct response
  is to re-probe the API, figure out what is actually true, rewrite the claim,
  and update the probe so it passes for the right reason.

Never loosen an assertion just to get it green. Either rewrite the claim to
match reality, or delete the claim if it is no longer useful.

## Two tiers of claim: unauthenticated vs. authenticated

Unlike Systembolaget's open frontend API (wine-guide), Booli's Open API is
**credentialled**: every data request must carry a `callerId` + HMAC `hash`
(see `api.md`). This splits our claims into two tiers:

- **Unauthenticated claims** — facts about routing, auth contract, and error
  behaviour that we can observe *without* credentials (e.g. "a request missing
  the auth params returns `403 FAILURE_MISSING_PARAM`"). These probes run in
  CI and on any machine, today, with no setup.
- **Authenticated claims** — facts about the *data* (response shape of `/sold`,
  query-parameter semantics, pagination). These require a real Booli identity.
  Their probes are **skipped** unless `BOOLI_CALLER_ID` and `BOOLI_KEY` are
  present in the environment, exactly as wine-guide's suite needs a live
  Systembolaget key. Until a key is obtained from `api@booli.se`, these claims
  are written but marked **PENDING** in `api.md` — never assert them as
  verified.

## Why `api.booli.se`, not the website GraphQL

`www.booli.se` (the consumer site, served from a Next.js app over a GraphQL
endpoint at `www.booli.se/graphql`) sits behind a Cloudflare **managed
challenge**: a plain `requests`/`curl` GET is answered with an HTTP 403
JS-challenge page, not data. Driving a real browser past the challenge is
possible but brittle and out of scope for a reproducible probe suite.

`api.booli.se` is a separate, purpose-built host (Apache/PHP, no Cloudflare)
that returns clean JSON and is explicitly designed for programmatic access to
listings and sold prices. We make it the documented data source. The Cloudflare
GraphQL path is recorded in `api.md` only as a noted alternative.

## Artefacts

All paths below are relative to the repo root.

- `api-docs/booli/tests/` — pytest probes. **The tests are the source of
  truth.** Every claim we make about the API is backed by at least one test
  here. Each test's docstring begins with a one-sentence statement of the claim.
- `api-docs/booli/api.md` — human-readable convenience documentation. A compiled
  summary of the claims, each tagged with the claim ID(s) that back it.
- `api-docs/booli/STRATEGY.md` — this file.

## Claim IDs

Each claim has a stable ID of the form `B###` (zero-padded, sequential). The ID
appears in three places:

1. The test function name: `test_B004_unknown_identity_rejected`.
2. The test docstring (first line is the claim itself).
3. `api-docs/booli/api.md`, inline as `[B004]`.

IDs are append-only. If a claim turns out to be wrong, rewrite it under the same
ID — git history retains what changed. Do not renumber.

## What makes a good claim

Prefer claims that help a future developer who is building on the API:

- **Structural**: "endpoint X returns a JSON object with key Y of type Z".
- **Behavioural**: "missing auth params give `403 FAILURE_MISSING_PARAM`",
  "an unknown `callerId` gives `403 FAILURE_IDENTITY_NOT_FOUND`".
- **Interop-critical**: "`booliId` on `/sold` is the same id space as `/listings`".

Avoid:

- **Volatile exact counts** ("there are exactly 12,431 sold homes in Nacka").
  Prefer lower bounds or ranges when the magnitude matters.
- **Restatements of obvious structure** ("the JSON has fields").

## Process for adding a claim

1. Identify an insight worth documenting.
2. Assign the next free `B###` ID.
3. Write a probe whose docstring's first line is a one-sentence claim.
4. Run it against the live API. Data-shape probes require credentials (see
   above); decorate them with `@requires_credentials`.
5. If it fails, probe until you understand the real behaviour, then rewrite the
   claim and the test together. Do not paper over the failure.
6. Add an entry referencing the ID to `api-docs/booli/api.md`.

## Handling volatility

Sold-price data grows daily. Write assertions that tolerate expected variation:

- Use `>=` on counts where the magnitude is the interesting fact.
- Do not assert on a specific sold home's price — those claims rot immediately.
- If you must name a specific `areaId`, pick a large, stable municipality
  (e.g. a kommun) unlikely to be renumbered, and prefer a set over a single id.

## Running the probes

Run from the repo root:

```sh
pip install -r requirements.txt

# Unauthenticated claims — run anywhere, no setup:
pytest api-docs/booli/tests/ -m "not requires_credentials"

# Everything, once you have an identity from api@booli.se:
export BOOLI_CALLER_ID=your-caller-id
export BOOLI_KEY=your-private-key
pytest api-docs/booli/tests/            # all claims
pytest api-docs/booli/tests/ -k B004    # one claim
pytest api-docs/booli/tests/ -v         # show each claim's docstring
```

Every run hits the live API. The auth probes need no credentials; the data
probes skip cleanly when `BOOLI_CALLER_ID` / `BOOLI_KEY` are unset.

## Getting an identity

Booli's Open API gates data behind a `callerId` + private `key` pair, issued by
Booli on request. The live API itself tells you where to ask: an unknown
identity is rejected with *"Please contact api@booli.se to receive an
identity."* `[B004]`. Email `api@booli.se` to request access; once granted, put
the pair in `BOOLI_CALLER_ID` / `BOOLI_KEY`.

## Scope

Only the `api.booli.se` Open API is in scope, and within it the home-sales use
case (`/sold`, plus `/areas` for resolving search regions). The consumer-site
GraphQL endpoint and the downstream scripts at the repo root that consume the
API are out of scope for this documentation effort.
