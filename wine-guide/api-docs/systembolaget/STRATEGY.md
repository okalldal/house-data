# Systembolaget API — Research Strategy

## Purpose

We are building durable knowledge of Systembolaget's undocumented
`api-extern.systembolaget.se` e-commerce API, so that future applications
can be built on top of it confidently. The output of this project is a body
of *verified* facts about how the API behaves.

## Core principle: we probe, we do not test

We do not own this API. We cannot assert what it *should* do — only observe
what it *does* do. Our pytest suite is a set of probes, not traditional
tests:

- If a probe passes, our documented claim is confirmed.
- If a probe fails, **our claim is wrong, not the API**. The correct
  response is to re-probe the API, figure out what is actually true,
  rewrite the claim, and update the probe so it passes for the right
  reason.

Never loosen an assertion just to get it green. Either rewrite the claim
to match reality, or delete the claim if it is no longer useful.

## Artefacts

All paths below are relative to the repo root.

- `api-docs/systembolaget/tests/` — pytest probes. **The tests are the
  source of truth.** Every claim we make about the API is backed by at
  least one test here. Each test's docstring begins with a one-sentence
  statement of the claim.
- `api-docs/systembolaget/api.md` — human-readable convenience
  documentation. A compiled summary of the claims, each tagged with the
  claim ID(s) that back it. This file may one day be generated from the
  tests; for now we maintain it by hand.
- `api-docs/systembolaget/STRATEGY.md` — this file.

## Claim IDs

Each claim has a stable ID of the form `C###` (zero-padded, sequential).
The ID appears in three places:

1. The test function name: `test_C014_search_exposes_vintage_field`.
2. The test docstring (first line is the claim itself).
3. `api-docs/systembolaget/api.md`, either inline as `[C014]` or as a
   trailing "verified by" note near the prose.

IDs are append-only. If a claim turns out to be wrong, rewrite it under
the same ID — git history retains what changed. Do not renumber.

## What makes a good claim

Prefer claims that help a future developer who is building on the API:

- **Structural**: "endpoint X returns a JSON object with key Y of type Z".
- **Behavioural**: "parameter P is silently ignored", "missing key gives
  HTTP 401", "Ordervaror products can still have physical store stock".
- **Interop-critical**: "productId is the same value on endpoints A and B".

Avoid:

- **Volatile exact counts** ("there are exactly 15,775 wines today").
  Prefer lower bounds or ranges when the magnitude matters.
- **Restatements of obvious structure** ("the JSON has fields").

## Process for adding a claim

1. Identify an insight worth documenting.
2. Assign the next free `C###` ID.
3. Write a probe whose docstring's first line is a one-sentence claim.
4. Run it against the live API.
5. If it fails, probe until you understand the real behaviour, then
   rewrite the claim and the test together. Do not paper over the failure.
6. Add an entry referencing the ID to `api-docs/systembolaget/api.md`.

## Handling volatility

The catalog and stock data change daily. Write assertions that tolerate
expected variation:

- Use `>=` on counts where the magnitude is the interesting fact.
- Do not assert on today's vintage for a specific product — those claims
  rot immediately.
- If you must name a specific productId, pick one stable enough that it
  is unlikely to be delisted (fast sortiment classics), and prefer a set
  of several over a single value.

## Running the probes

Run from the repo root:

```sh
pip install -r requirements.txt
pytest api-docs/systembolaget/tests/                # all claims
pytest api-docs/systembolaget/tests/ -k C014        # one claim
pytest api-docs/systembolaget/tests/ -v             # show each claim's docstring
```

Every run hits the live API. A valid `Ocp-Apim-Subscription-Key` is baked
into `api-docs/systembolaget/tests/conftest.py`; if the suite starts
returning 401s, refresh it from systembolaget.se DevTools.

## Scope

Only the `api-extern.systembolaget.se` API is in scope. The Munskänkarna
API has its own research subtree under `api-docs/munskankarna/`; the
downstream scripts at the repo root that consume either API are out of
scope for this documentation effort.
