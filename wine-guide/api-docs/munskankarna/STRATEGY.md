# Munskänkarna API — Research Strategy

## Purpose

We are building durable knowledge of Munskänkarna's undocumented
Vinlocus search API at `munskankarna.se/umbraco/surface/winesearch/`,
so that `scrape_wines.py` and any future consumers can rely on its
quirks with confidence rather than folklore. The output of this
subproject is a body of *verified* facts about how the API behaves.

This file mirrors the approach in
`api-docs/systembolaget/STRATEGY.md` — the two APIs are different but
the discipline is the same.

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

- `api-docs/munskankarna/tests/` — pytest probes. **The tests are the
  source of truth.** Every claim we make about the API is backed by at
  least one test here. Each test's docstring begins with a one-sentence
  statement of the claim.
- `api-docs/munskankarna/api.md` — human-readable convenience
  documentation. A compiled summary of the claims, each tagged with the
  claim ID(s) that back it.
- `api-docs/munskankarna/STRATEGY.md` — this file.

## Claim IDs

Each claim has a stable ID of the form `M###` (zero-padded, sequential).
The `M` prefix distinguishes Munskänkarna claims from Systembolaget's
`C###` claims — grepping for `M001` should never collide with the
other API's namespace.

The ID appears in three places:

1. The test function name: `test_M001_listwinebottles_wraps_around`.
2. The test docstring (first line is the claim itself).
3. `api-docs/munskankarna/api.md`, either inline as `[M001]` or as a
   trailing "verified by" note near the prose.

IDs are append-only. If a claim turns out to be wrong, rewrite it under
the same ID — git history retains what changed. Do not renumber.

## What makes a good claim

Prefer claims that help a future developer who is building on the API:

- **Structural**: "endpoint X returns a JSON object with key Y of type Z".
- **Behavioural**: "the response wraps around on the last page instead
  of returning a partial", "the unfiltered list duplicates each row
  once per local section".
- **Interop-critical**: "`wineBottleExternalLink.text` is the
  Systembolaget article number, sometimes the short legacy form".

Avoid:

- **Volatile exact counts** ("there are exactly 684 sessions today").
  Prefer lower bounds or ranges when the magnitude matters.
- **Restatements of obvious structure** ("the JSON has fields").

## Process for adding a claim

1. Identify an insight worth documenting. Good candidates live as
   comments in `scrape_wines.py` today — the 52× duplication, the
   wrap-around behaviour, the multi-value session filter.
2. Assign the next free `M###` ID.
3. Write a probe whose docstring's first line is a one-sentence claim.
4. Run it against the live API.
5. If it fails, probe until you understand the real behaviour, then
   rewrite the claim and the test together. Do not paper over the
   failure.
6. Add an entry referencing the ID to `api-docs/munskankarna/api.md`.

## Handling volatility

The session list and published tasting notes grow over time. Write
assertions that tolerate expected variation:

- Use `>=` on counts where the magnitude is the interesting fact.
- Do not assert on a specific session's exact wine count — new notes
  can be added.
- If you must name a specific session, pick one old enough to be
  closed (no new notes will land).

## Running the probes

Run from the repo root:

```sh
pip install -r requirements.txt
pytest api-docs/munskankarna/tests/                # all claims
pytest api-docs/munskankarna/tests/ -k M001        # one claim
pytest api-docs/munskankarna/tests/ -v             # show each claim's docstring
```

Every run hits the live API. No key is required — Munskänkarna's
Umbraco surface controllers are publicly reachable — but we send a
polite `User-Agent` identifying the scraper.

## Scope

Only the `munskankarna.se/umbraco/surface/winesearch/` endpoints are
in scope. The Systembolaget API has its own research subtree under
`api-docs/systembolaget/`; downstream scripts at the repo root that
consume either API are out of scope for this documentation effort.
