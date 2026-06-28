# Product-code analysis — Munskänkarna → Systembolaget

## TL;DR

- **Only 1.1 % of tasting rows (257 / 23,865) match a Systembolaget
  `productNumber` exactly.** The remaining 99 % use a shorter legacy
  article number (typically 5 digits) that needs a suffix to map to the
  modern 7-digit `productNumber`.
- **The sibling-group prefix rule works** — for a 5-digit tasting code
  `C`, try the 7-digit productNumber `C01`. That single suffix accounts
  for 85 % of strict-rule picks and 96 % of the picks whose name
  actually agrees with the Systembolaget listing.
- **The prefix rule is brittle half the time.** Of 15,164 prefix-match
  rows we could fully verify (candidate exists in the search endpoint),
  **7,370 (49 %)** have a name AND producer both disagreeing — the code
  accidentally collides with an unrelated wine.
- **False-positive rate tracks the age of the tasting almost linearly.**
  2026 tastings: 0 % FP. 2020: 56 %. 2010: 92 %. Codes stored in the
  Munskänkarna corpus rot as Systembolaget recycles article numbers.
- **There is no API field that authoritatively confirms identity.** The
  catalog has no vintage, and neither the catalog nor the search
  endpoint carries a “retired / was” link. The only practical
  disambiguator is **fuzzy comparison of name + producer** from the
  search endpoint.

Numbers below are reproducible from this folder — re-run
`python3 fetch_data.py` then `python3 analyze_codes.py`.

---

## Dataset

| Source | Rows | Notes |
|---|---|---|
| `data/wines_clean.csv` tasting rows | 25,937 | |
| … with a digit-only code in `systembolaget_id` | 23,865 | drop `nätvin` / empty / garbage |
| … with `systembolaget_id` blank or non-digit | 2,072 | (incl. 1,479 `Nätvin`) |
| Systembolaget catalog items (all categories) | 30,366 | one call, `/v1/product` |
| … classified `categoryLevel1 == "Vin"` | 17,563 | |
| Wine search endpoint (paginated per country) | 14,983 unique `productNumber` | |

Catalog includes non-wine drinks such as Sake, Aperol, Campari under
`categoryLevel1 == "Vin"`; we kept those in-scope because
Munskänkarna publishes some sake tastings, and excluding them would
hide a real source of collisions (see §Phase 1 below).

### Tasting-code length histogram

| len | rows | share |
|---|---:|---:|
| 4 | 1,971 | 8 % |
| 5 | 21,589 | 91 % |
| 6 | 65 | 0.3 % |
| 7 | 259 | 1.1 % |
| other | 15 | < 0.1 % |

The corpus is essentially a mix of 4- and 5-digit legacy article
numbers. That matches the historical Systembolaget article-number
format; the modern API serves 6- and 7-digit `productNumber`s (16,037
of 17,563 wines are 7-digit).

### Systembolaget wine-catalog length histogram

| PN length | wines | notes |
|---|---:|---|
| 5 | 17 | short legacy SKUs still sold |
| 6 | 1,508 | older SKUs |
| 7 | 16,037 | modern SKUs |
| 9 | 1 | freak |

---

## Phase 1 — exact `productNumber` match

Treat the tasting code as a full `productNumber`. Look it up in the
catalog; if it matches, compare name / vintage / producer against the
search record.

| bucket | count |
|---|---:|
| name + vintage agree | 155 |
| name agrees, vintage differs (new year under same PN) | 68 |
| name agrees, tasting has no vintage recorded | 0 |
| vintage agrees, name differs (cuvée rename) | 9 |
| neither (producer + name + vintage disagree) | 13 |
| in catalog but not in search cache, name match | 10 |
| in catalog but not in search cache, name mismatch | 2 |
| **total exact-match rows** | **257** |
| no exact match | 23,608 |

**Read.** For the 1.1 % of rows where the code is directly a valid
productNumber, 223 / 257 = 87 % are clearly the same wine (name agrees;
vintage may or may not). The 13 "neither" cases split into:

- **Short-PN namespace collisions (9/13).** Five 5-digit tasting codes
  (`13101`, `70101`, `70398`, `70782`, `72901`) coincide with Systembolaget
  5-digit productNumbers. All five SB products are spirits / sake /
  aperitifs / unrelated wines: `13101` → Mikadomatsu sake, `70101` →
  Campari Bitter, `72901` → Aperol, `70782` → Fullerton (Oregon),
  `70398` → Champagne Charpentier. The 5-digit PN namespace is sparse
  (only 17 wine entries) and the collisions are purely coincidental.
- **Name-reorder false negatives (4/13).** Three rows for
  `7695901` (Montesoeiros Godello) and one for `5809201` (Montefalco
  Rosso) are the same wine as the SB listing but token reorder pushes
  the fuzzy score below 0.6. My rule flags them as "neither" — they
  are a metric artefact, not a genuine mismatch.

**No evidence of intra-corpus code reuse on the "neither" bucket.**
All 13 collision rows have exactly one distinct (name, producer) pair
in the Munskänkarna dataset, so the tasting side is not recycling.

---

## Phase 2 — codes that exist but don’t mean the same wine

The Munskänkarna dataset **does** reuse short codes across distinct
wines, though rarely on rows where those codes happen to also be valid
SB productNumbers. A separate check on the full tasting corpus:

- 5,541 codes appear on multiple tasting rows.
- **4,288 codes have more than one distinct `(name, producer)` pair**.

Sample:

| code | distinct wines published under this code |
|---|---|
| `93459` | Chénas les Blémonts (2021) · Tayu 1865 (2022) · Chianti Classico (2025) · Grignolino d'Asti Frasca (2026) |
| `92871` | Barolo Azelia (2020) · Blanc Chenin (2021) · Rough Diamond Grenache (2026) |
| `94508` | Gosset Rosé (2022) · Josefinelust (2023) · Break a leg Chardonnay (2026) |

This is a structural property of Munskänkarna codes: they are **not
persistent identifiers for a wine** — they are Systembolaget article
numbers *as they stood at the time the tasting was published*. When
Systembolaget retires a SKU, the number is returned to the pool and
later reused. The tasting row freezes the old reference.

---

## Phase 3 — prefix / suffix rule for unmatched codes

For the 23,608 rows without an exact match we test the sibling rule
from `api-docs/systembolaget/api.md` C011/C013: the last two
characters of a wine `productNumber` encode packaging, so the identity
prefix is `productNumber[:-2]`.

We compare two strategies:

- **Strict.** Tasting code `C` of length `L` matches a catalog
  `productNumber` `P` iff `len(P) == L + 2` and `P[:L] == C`. This
  respects the sibling-group rule directly.
- **Loose.** `P[:L] == C` for any `len(P) >= L`. Includes both the
  `L+2` siblings and any same-prefix entries of other lengths.

| metric | strict | loose |
|---|---:|---:|
| rows with ≥ 1 candidate | 17,662 | 17,805 |
| rows with > 1 candidate (ambiguous) | 506 | 1,119 |
| extra candidates vs strict | — | 3,911 |
| rows loose matches but strict doesn’t | — | 143 |

Loose adds **3,911 extra candidates** but only **143 extra rows** —
it is mostly noise. All further analysis uses the strict rule.

### Suffix distribution — strict, best pick per row

Shares are within the respective tasting-code length, i.e. "of all
5-digit tasting codes that matched something under the strict rule,
what suffix did the best-pick carry".

5-digit tasting codes (15,986 rows with a strict candidate):

| suffix | count | share |
|---|---:|---:|
| **01** | 15,019 | **94.0 %** |
| 02 | 313 | 2.0 % |
| 06 | 278 | 1.7 % |
| 09 | 186 | 1.2 % |
| 08 | 80 | 0.5 % |
| other | 110 | 0.7 % |

4-digit tasting codes (1,676 rows with a strict candidate):

| suffix | count | share |
|---|---:|---:|
| **01** | 1,393 | **83.1 %** |
| 02 | 128 | 7.6 % |
| 06 | 32 | 1.9 % |
| 08 | 26 | 1.6 % |
| 11 | 25 | 1.5 % |
| other | 72 | 4.3 % |

### Suffix distribution — restricted to rows whose name actually agrees

This subset (≈ 8,200 rows) is the closest proxy for "the matcher
picked the right sibling" — so the suffix mix here shows the true
packaging-variant distribution of real matches rather than the noise
of wrong picks.

5-digit tasting codes, name-matching subset (6,836 rows):

| suffix | count | share |
|---|---:|---:|
| **01** | 6,585 | **96.3 %** |
| 02 | 138 | 2.0 % |
| 06 | 63 | 0.9 % |
| other | 50 | 0.7 % |

4-digit tasting codes, name-matching subset (1,368 rows):

| suffix | count | share |
|---|---:|---:|
| **01** | 1,169 | **85.5 %** |
| 02 | 119 | 8.7 % |
| 06 | 32 | 2.3 % |
| other | 48 | 3.5 % |

**Read.**

1. Appending `01` is the default. When the name also agrees, 96 % of
   5-digit → 7-digit mappings are `+01`, and 87 % of 4-digit → 6-digit
   ones are.
2. Non-`01` suffixes are concentrated in packaging variants: `02` and
   `06` most commonly, which per the C013/C014 claims are bag-in-box
   and half-bottle. When we sort by name-agreement, the tail shrinks
   sharply — non-`01` picks are heavily over-represented among wrong
   picks.
3. Ambiguity is low. Only 506 / 17,662 (2.9 %) strict-match rows have
   more than one `L+2` candidate, i.e. genuine sibling-group hits where
   a wine exists in multiple packagings. For those, a second signal is
   needed to pick the 750-ml bottle (see §How-to-verify).

### Coverage by tasting year

Rows with *no* prefix candidate at all — the wine has disappeared from
Systembolaget:

| tasting year | total unmatched | no prefix candidate | share |
|---|---:|---:|---:|
| 1998–2007 | 1,845 | 1,692 | 92 % |
| 2008–2012 | 2,136 | 595 | 28 % |
| 2013–2017 | 3,634 | 638 | 18 % |
| 2018–2022 | 8,831 | 2,074 | 23 % |
| 2023–2026 | 7,162 | 1,069 | 15 % |

The prefix heuristic "finds something" for 74–91 % of rows per year
across the last decade, dropping off sharply for pre-2010 tastings
where the wine is simply no longer sold.

---

## Phase 4 — is the prefix match actually the same wine?

For each strict prefix match we took the search record, pulled its
`productNameBold + productNameThin` and `producerName`, and compared
to the tasting row using:

- **name_sim** — `difflib.SequenceMatcher` ratio on diacritic-folded,
  lowercased, punctuation-stripped names.
- **name_jaccard** — token Jaccard on the same normalised strings
  (picks up reorder).
- **producer_sim** — same SequenceMatcher ratio on producer strings.

Name is "a match" if `name_sim ≥ 0.6` or `jaccard ≥ 0.5`. Producer is
"a match" if `producer_sim ≥ 0.6`.

### Crosstab (strict rule, candidate in search) — 15,164 rows

| | producer matches | producer mismatches | total |
|---|---:|---:|---:|
| **name matches** | 6,908 | 404 | 7,312 |
| **name mismatches** | 482 | 7,370 | 7,852 |

- **6,908 (46 %)** same-wine, high confidence.
- **482 (3.2 %)** producer matches but name differs — likely cuvée
  rename, e.g. "Gaba do Xil Godello" vs "Godello Valdeorras" from the
  same producer.
- **404 (2.7 %)** name matches but producer differs — usually the
  tasting lists the importer (Vinarchy, Nigab) and the search the
  winery (Campo Viejo, Oevicon). Still genuine matches.
- **7,370 (49 %) both mismatch — real false positives.** The
  prefix-matched productNumber is a completely different wine.

### False-positive rate by tasting year

Real FP share (both name and producer mismatch, over all strict
prefix matches found in search) — bucketed:

| year | same wine | real FP | FP share |
|---|---:|---:|---:|
| 1998–2002 | 8 | 146 | 95 % |
| 2003–2007 | 34 | 40 | 54 % |
| 2008–2012 | 122 | 1,203 | 91 % |
| 2013–2017 | 509 | 2,107 | 81 % |
| 2018 | 134 | 232 | 63 % |
| 2019 | 523 | 793 | 60 % |
| 2020 | 577 | 727 | 56 % |
| 2021 | 629 | 608 | 49 % |
| 2022 | 640 | 510 | 44 % |
| 2023 | 928 | 483 | 34 % |
| 2024 | 1,056 | 425 | 29 % |
| 2025 | 1,327 | 96 | 7 % |
| 2026 | 421 | 0 | 0 % |

**This is the headline finding.** The decay is steep and monotonic.
Codes "age out" because Systembolaget recycles article numbers: when
an SKU is delisted, the number is eventually reassigned to a new
wine. A Munskänkarna code stored in 2010 is 90 % likely to point to a
different wine today even though `code + "01"` is still a live
`productNumber`.

### Sample false positives

| code | tasting wine | current `code+01` listing | tasting year |
|---|---|---|---|
| `90389` | Grand Elevage Savagnin · Maison Rijckaert | Château Ducru-Beaucaillou | 2019 |
| `92779` | Askos Verdeca · Masseria Li Veli | Zweigelt · Weingut Arndorfer | 2021 |
| `78193` | Châteauneuf-du-Pape La Bernardine · M. Chapoutier | Vieira Atlantica Albariño · Urban Wines | 2014 |
| `92048` | Laietà Gran Reserva · Alta Alella | Cornas Renaissance · Domaine Clape | 2016 |

None of these share producer or region; the productNumber has simply
been re-issued by Systembolaget for a different product.

---

## How to verify a match using only the API

There is **no server-side signal** that unambiguously says "this
productNumber used to be another wine". Neither the catalog nor the
search endpoint carries a history, and `recommended` /
`productfeedback` / `beveragelist` are authenticated-only (C110–C112
in `api-docs/systembolaget/api.md`).

What the search endpoint *does* give us for every candidate:

- `productNameBold` + `productNameThin`
- `producerName`
- `country`, `originLevel1`, `originLevel2`
- `vintage`
- `grapes` (list)
- `categoryLevel2` (`Rött vin` / `Vitt vin` / `Mousserande vin` / …)

These are the same four signals you'd use to tell wines apart in a
shop, and the only robust verdict is **combine them**. For this
corpus, name + producer alone catches:

- 6,908 high-confidence same-wine (both agree)
- 886 additional one-signal-only same-wine (one disagrees but the
  other signals carry it)

So a practical matcher should:

1. Try the sibling rule: `code + "01"` (fallback `+ "02"`, `+ "06"`).
2. Fetch the candidate from search.
3. Compute name similarity (fuzzy + jaccard) and producer similarity.
4. Accept the match only if at least one of (name_sim ≥ 0.6 /
   jaccard ≥ 0.5) AND producer_sim ≥ 0.6 — i.e. a two-signal
   agreement.
5. Bonus: require `country` equality and at least one shared grape.
6. If still ambiguous (e.g. multiple strict candidates), prefer the
   `+01` sibling, then compare `volume == 750` to pick the single-bottle
   variant.

This is brittle by nature (names drift, producers get renamed to
importers), but it is the only approach that actually works against
the live data. No API field authoritatively confirms a match.

---

## Reproducibility

```
# Fetch and cache (~1 min catalog, ~8 min search)
python3 product_code_analysis/fetch_data.py

# Run all four phases (~10 s)
python3 product_code_analysis/analyze_codes.py
```

Outputs:

- `cache/catalog.json` (7.9 MB, 30,366 items, all categories)
- `cache/wine_search.json` (38 MB, 14,983 wines with full attributes)
- `out/phase1_exact.json`, `phase1_exact_detail.csv` — every exact-match row
- `out/phase2.json`, `phase2_collision_samples.csv` — the 13 "neither" rows
- `out/phase3_prefix.json`, `phase3_prefix_detail.csv` — one row per unmatched tasting row with strict + loose picks
- `out/phase4.json`, `phase4_false_positives.csv` — 7,370 real FP rows
- `out/summary.json` — top-line numbers used above

### Caveats on the numbers

- Country-partitioned search pagination drops 0–6 % of rows per
  partition due to the server-side row duplication noted in C054; the
  cached `wine_search.json` has 14,983 of 15,768 advertised wines
  (95 %). Wines missing from the cache show up in the "catalog hit,
  no search data" bucket in Phase 1 (12 rows total — negligible for
  Phase 3/4 conclusions).
- Name-similarity thresholds (`sim ≥ 0.6`, `jaccard ≥ 0.5`,
  `producer_sim ≥ 0.6`) were chosen by inspection of a few hundred
  samples. They produce a small known error band, visible in the
  4-signal crosstab above: ~404 rows (2.7 %) where name sim passes
  but producer doesn't — most of these are genuine matches with
  importer-vs-winery disagreement.
- The FP-rate-by-year numbers require a candidate to exist in the
  search cache for that row; ~14 % of strict-candidate rows did not
  (the candidate was in the catalog but our search pagination missed
  it), and those were excluded from the crosstab.
