"""
analyze_codes.py  -  Reproducible product-code matching analysis.

Reads:
  ../data/wines_clean.csv
  cache/catalog.json
  cache/wine_search.json

Writes:
  out/phase1_exact.json              - exact-match counts and per-bucket samples
  out/phase1_exact_detail.csv        - one row per tasting row with its match verdict
  out/phase2_collision_samples.csv   - exact-match-but-neither-name-nor-vintage
  out/phase3_prefix.json             - suffix distribution, match rates
  out/phase3_prefix_detail.csv       - one row per unmatched code with prefix-match verdict
  out/phase4_false_positives.csv     - prefix matches with dubious name overlap
  out/summary.json                   - top-line numbers for the writeup
"""

import csv
import json
import re
import sys
import unicodedata
from collections import Counter, defaultdict
from difflib import SequenceMatcher
from pathlib import Path

ROOT = Path(__file__).parent
DATA_CSV = ROOT.parent / "data" / "wines_clean.csv"
CATALOG = ROOT / "cache" / "catalog.json"
SEARCH = ROOT / "cache" / "wine_search.json"
OUT = ROOT / "out"


# ── Text normalisation ──────────────────────────────────────────────────────

_WS_RE = re.compile(r"\s+")


def norm_name(s: str) -> str:
    """
    Normalise a wine name for comparison:
      - Lowercase, strip, collapse whitespace
      - Unicode NFKD + drop combining marks (Chénas -> Chenas)
      - Drop non-alphanumeric except space
    Munskänkarna often writes "Vina Bosconia" vs Systembolaget "Viña Bosconia",
    or "Chateau ..." vs "Château ...", so folding diacritics matters.
    """
    if not s:
        return ""
    s = s.strip().lower()
    s = unicodedata.normalize("NFKD", s)
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = re.sub(r"[^\w\s]", " ", s)
    s = _WS_RE.sub(" ", s).strip()
    return s


def name_sim(a: str, b: str) -> float:
    """SequenceMatcher ratio on normalised names."""
    a, b = norm_name(a), norm_name(b)
    if not a or not b:
        return 0.0
    return SequenceMatcher(None, a, b).ratio()


def name_tokens(s: str):
    return set(norm_name(s).split())


def jaccard(a: str, b: str) -> float:
    ta, tb = name_tokens(a), name_tokens(b)
    if not ta or not tb:
        return 0.0
    return len(ta & tb) / len(ta | tb)


# ── Data loading ────────────────────────────────────────────────────────────


def load_tasting_rows():
    rows = []
    with DATA_CSV.open(encoding="utf-8") as f:
        for row in csv.DictReader(f):
            sid = (row.get("systembolaget_id") or "").strip()
            if not sid:
                continue
            # Lowercased "nätvin" etc. leaked through clean_wines (only the
            # exact "Nätvin" casing is filtered). Drop the obvious non-digit
            # garbage here too.
            if not sid.isdigit():
                continue
            rows.append({
                "code": sid,
                "name": row.get("name", "") or "",
                "producer": row.get("producer", "") or "",
                "year": (row.get("year") or "").strip(),
                "year_raw": (row.get("year_raw") or "").strip(),
                "activity_name": row.get("activity_name", "") or "",
                "activity_date": row.get("activity_publish_date", "") or "",
                "price_munsk": (row.get("price") or "").strip(),
                "volume_munsk": (row.get("volume") or "").strip(),
            })
    return rows


def load_catalog():
    cat = json.loads(CATALOG.read_text())
    # Index by productNumber. Keep only wine items — a tasting code must be a
    # wine product, and prefix-matching against spirits/beer would be noise.
    return {c["productNumber"]: c for c in cat if c.get("categoryLevel1") == "Vin"}


def load_search():
    wines = json.loads(SEARCH.read_text())
    return {w["productNumber"]: w for w in wines}


# ── Phase 1: exact-match analysis ───────────────────────────────────────────


def compare_to_sb(row, search_hit, catalog_hit):
    """
    Compare a tasting row to a (search_hit, catalog_hit) Systembolaget record
    pair. Produces all the scalar signals other code will aggregate.

    - search_hit (dict or None): row from /productsearch/search; has vintage,
      producerName, country, etc.
    - catalog_hit (dict or None): row from /product; sparse.
    """
    sb_name = ""
    sb_producer = ""
    sb_country = ""
    sb_vintage = None
    in_search = search_hit is not None
    if search_hit is not None:
        sb_name = search_hit.get("productNameBold") or ""
        thin = search_hit.get("productNameThin") or ""
        sb_name = (sb_name + " " + thin).strip()
        sb_producer = search_hit.get("producerName") or ""
        sb_country = search_hit.get("country") or ""
        sb_vintage = search_hit.get("vintage")
    elif catalog_hit is not None:
        sb_name = catalog_hit.get("productNameBold") or ""

    sim = name_sim(row["name"], sb_name)
    jac = jaccard(row["name"], sb_name)
    # Name considered a match if fuzzy sim >= 0.6 OR token jaccard >= 0.5
    # (sim handles spelling drift, jaccard handles token reorder).
    name_matches = sim >= 0.6 or jac >= 0.5

    prod_sim = name_sim(row["producer"], sb_producer) if sb_producer else 0.0
    producer_matches = prod_sim >= 0.6 if sb_producer else None

    vintage_match = None
    if in_search and row["year"]:
        if sb_vintage is None:
            vintage_match = False
        else:
            try:
                vintage_match = int(sb_vintage) == int(row["year"])
            except (TypeError, ValueError):
                vintage_match = False

    return {
        "sb_name": sb_name,
        "sb_producer": sb_producer,
        "sb_country": sb_country,
        "sb_vintage": sb_vintage,
        "in_search": in_search,
        "name_sim": round(sim, 3),
        "name_jaccard": round(jac, 3),
        "producer_sim": round(prod_sim, 3),
        "name_matches": name_matches,
        "producer_matches": producer_matches,
        "vintage_match": vintage_match,
    }


def classify_exact(row, search_hit, catalog_hit):
    """
    Exact-code match verdict. Buckets:
      name+vintage               - both name and vintage agree
      name_only                  - name agrees, vintage differs (new vintage
                                   under same productNumber)
      name_only_no_vintage       - name agrees; tasting has no year recorded
      vintage_only               - vintage agrees but name differs
      neither                    - both name and vintage disagree; likely a
                                   reused code or a mismatch
      no_search_data             - productNumber is in catalog but not in
                                   search cache (so we don't have vintage/etc.)
    """
    cmp = compare_to_sb(row, search_hit, catalog_hit)

    if not cmp["in_search"]:
        bucket = "no_search_data_" + ("name_match" if cmp["name_matches"] else "name_mismatch")
    else:
        nm = cmp["name_matches"]
        vm = cmp["vintage_match"]
        if nm and vm is True:
            bucket = "name+vintage"
        elif nm and vm is False:
            bucket = "name_only"
        elif nm and vm is None:
            bucket = "name_only_no_vintage"
        elif (not nm) and vm is True:
            bucket = "vintage_only"
        elif (not nm) and vm is False:
            bucket = "neither"
        else:  # vm is None, nm is False
            bucket = "neither_no_vintage"

    out = dict(cmp)
    out["bucket"] = bucket
    return out


def phase1(tasting_rows, catalog_by_pn, search_by_pn):
    detail_rows = []
    buckets = Counter()
    exact_match_count = 0
    no_match_count = 0

    for row in tasting_rows:
        code = row["code"]
        search_hit = search_by_pn.get(code)
        catalog_hit = catalog_by_pn.get(code)
        if search_hit is None and catalog_hit is None:
            no_match_count += 1
            continue
        exact_match_count += 1
        v = classify_exact(row, search_hit, catalog_hit)
        buckets[v["bucket"]] += 1
        detail_rows.append({
            "code": code,
            "tasting_name": row["name"],
            "tasting_producer": row["producer"],
            "tasting_year": row["year"],
            "tasting_activity_date": row["activity_date"],
            "sb_name": v["sb_name"],
            "sb_producer": v["sb_producer"],
            "sb_country": v["sb_country"],
            "sb_vintage": v["sb_vintage"],
            "in_search": v["in_search"],
            "name_sim": v["name_sim"],
            "name_jaccard": v["name_jaccard"],
            "producer_sim": v["producer_sim"],
            "vintage_match": v["vintage_match"],
            "bucket": v["bucket"],
        })

    # Write CSV
    with (OUT / "phase1_exact_detail.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(detail_rows[0].keys()) if detail_rows else [])
        w.writeheader()
        w.writerows(detail_rows)

    summary = {
        "tasting_rows_with_digit_code": len(tasting_rows),
        "exact_productNumber_match": exact_match_count,
        "no_exact_match": no_match_count,
        "buckets": dict(buckets),
    }
    (OUT / "phase1_exact.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False))
    return detail_rows, summary


# ── Phase 2: collision analysis ─────────────────────────────────────────────


def phase2(detail_rows, tasting_rows):
    """
    Inspect the 'neither' bucket - tasting rows whose code exactly matches an
    SB productNumber but the name AND vintage disagree. Patterns we want to see:
      - old reused codes (tasting predates the current SB listing by a lot)
      - short 4-5 digit codes that coincidentally appear as modern 6-7 digit
        productNumbers (should be rare - see length mismatch)
      - multiple distinct tasting entries for the same code across years
      - producer agreement (if producers match, the collision may be a label
        refresh rather than a different wine).
    """
    history = defaultdict(list)
    for r in tasting_rows:
        history[r["code"]].append(r)

    collisions = [
        d for d in detail_rows
        if d["bucket"] in ("neither", "neither_no_vintage")
    ]

    rows_out = []
    for d in collisions:
        code = d["code"]
        tastings_for_code = history.get(code, [])
        distinct_wines = set((t["name"], t["producer"]) for t in tastings_for_code)
        earliest = min((t["activity_date"] for t in tastings_for_code), default="")
        latest = max((t["activity_date"] for t in tastings_for_code), default="")
        rows_out.append({
            **d,
            "code_len": len(code),
            "distinct_tasting_wines_for_code": len(distinct_wines),
            "tasting_code_earliest_session": earliest,
            "tasting_code_latest_session": latest,
        })

    with (OUT / "phase2_collision_samples.csv").open("w", newline="", encoding="utf-8") as f:
        if rows_out:
            w = csv.DictWriter(f, fieldnames=list(rows_out[0].keys()))
            w.writeheader()
            w.writerows(rows_out)

    len_hist = Counter(r["code_len"] for r in rows_out)
    reused_code_count = sum(1 for r in rows_out if r["distinct_tasting_wines_for_code"] > 1)
    # Producer match on neither-bucket rows
    prod_match_rows = sum(1 for r in rows_out if (r.get("producer_sim") or 0) >= 0.6)
    # Earliest tasting for these collision codes
    old_tasting_rows = sum(
        1 for r in rows_out
        if r["tasting_code_earliest_session"] and r["tasting_code_earliest_session"][:4] < "2015"
    )
    summary = {
        "collision_rows": len(rows_out),
        "collision_code_len_histogram": dict(sorted(len_hist.items())),
        "collision_rows_where_code_is_reused_within_tasting_dataset": reused_code_count,
        "collision_rows_with_matching_producer": prod_match_rows,
        "collision_rows_with_earliest_tasting_before_2015": old_tasting_rows,
    }
    (OUT / "phase2.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False))
    return summary


# ── Phase 3: prefix / suffix analysis ───────────────────────────────────────


def phase3(tasting_rows, catalog_by_pn, search_by_pn):
    """
    For tasting codes with NO exact productNumber match, try the sibling
    strategy: the code is a prefix of one or more productNumbers, most often
    with a 2-digit packaging suffix (01, 02, 06, 08, ...).

    We run TWO strategies in parallel so we can report on each:

      strict  - tasting code `c` (len L) matches PN `p` iff len(p) == L+2 AND
                p[:L] == c. This is the canonical sibling-group rule from
                CLAUDE.md (identity prefix = first N-2 chars of the PN).
      loose   - p[:L] == c for any p of any length. This over-matches across
                PN-length boundaries (e.g. 5-digit code matching both a
                7-digit intended sibling and an unrelated 6-digit wine).

    The difference between strict and loose quantifies how many "matches"
    the naive prefix rule invents.
    """
    by_prefix_strict = defaultdict(list)       # (L, prefix) -> [pn], pn len == L+2
    by_prefix_loose = defaultdict(list)        # (L, prefix) -> [pn], any pn len >= L
    for pn in catalog_by_pn:
        for L in range(3, min(len(pn), 7) + 1):
            by_prefix_loose[(L, pn[:L])].append(pn)
        # Strict: contribute only when len(pn) == L+2
        sL = len(pn) - 2
        if sL >= 3:
            by_prefix_strict[(sL, pn[:sL])].append(pn)

    unmatched_rows = [r for r in tasting_rows if r["code"] not in catalog_by_pn]

    detail = []
    all_suffix_counter = Counter()     # (code_len, pn_len, suffix) -> count
    any_match_count = 0
    ambiguous_match_count = 0

    # Counters for strict vs loose
    strict_any = 0
    strict_ambig = 0
    loose_any = 0
    loose_ambig = 0
    strict_suffix = Counter()   # (L, suffix) -> count
    loose_suffix = Counter()    # (L, pn_len, suffix) -> count
    # How often does loose match something that strict didn't?
    loose_only_extra = 0        # rows where loose has >0 but strict has 0
    loose_added_candidates = 0  # total extra PNs from loose vs strict

    def _pick_best(row, cand_list):
        best = None
        best_score = -1.0
        best_cmp = None
        for c in cand_list:
            cmp = compare_to_sb(row, search_by_pn.get(c), catalog_by_pn.get(c))
            score = cmp["name_sim"] + 0.3 * cmp["producer_sim"]
            if score > best_score:
                best_score = score
                best = c
                best_cmp = cmp
        if best_cmp is None:
            best_cmp = {
                "sb_name": "", "sb_producer": "", "sb_country": "",
                "sb_vintage": "", "in_search": False,
                "name_sim": 0.0, "name_jaccard": 0.0, "producer_sim": 0.0,
                "name_matches": False, "producer_matches": None,
                "vintage_match": None,
            }
        return best, best_cmp

    for row in unmatched_rows:
        code = row["code"]
        L = len(code)
        strict_cand = by_prefix_strict.get((L, code), []) if 3 <= L <= 7 else []
        loose_cand = by_prefix_loose.get((L, code), []) if 3 <= L <= 7 else []

        if strict_cand:
            strict_any += 1
            if len(strict_cand) > 1:
                strict_ambig += 1
            for c in strict_cand:
                strict_suffix[(L, c[L:])] += 1
        if loose_cand:
            loose_any += 1
            if len(loose_cand) > 1:
                loose_ambig += 1
            for c in loose_cand:
                loose_suffix[(L, len(c), c[L:])] += 1
        extra = set(loose_cand) - set(strict_cand)
        if not strict_cand and loose_cand:
            loose_only_extra += 1
        loose_added_candidates += len(extra)

        # Best picks for each strategy
        strict_best, strict_cmp = _pick_best(row, strict_cand)
        loose_best, loose_cmp = _pick_best(row, loose_cand)

        detail.append({
            "code": code,
            "code_len": L,
            "tasting_name": row["name"],
            "tasting_producer": row["producer"],
            "tasting_year": row["year"],
            "tasting_activity_date": row["activity_date"],
            # Strict
            "strict_n": len(strict_cand),
            "strict_best_pn": strict_best or "",
            "strict_suffix": (strict_best[L:] if strict_best and len(strict_best) > L else ""),
            "strict_sb_name": strict_cmp["sb_name"],
            "strict_sb_producer": strict_cmp["sb_producer"],
            "strict_sb_country": strict_cmp["sb_country"],
            "strict_sb_vintage": strict_cmp["sb_vintage"],
            "strict_in_search": strict_cmp["in_search"],
            "strict_name_sim": strict_cmp["name_sim"],
            "strict_name_jaccard": strict_cmp["name_jaccard"],
            "strict_producer_sim": strict_cmp["producer_sim"],
            "strict_name_matches": strict_cmp["name_matches"],
            "strict_producer_matches": strict_cmp["producer_matches"],
            "strict_vintage_match": strict_cmp["vintage_match"],
            # Loose
            "loose_n": len(loose_cand),
            "loose_best_pn": loose_best or "",
            "loose_best_pn_len": (len(loose_best) if loose_best else 0),
            "loose_sb_name": loose_cmp["sb_name"],
            "loose_name_sim": loose_cmp["name_sim"],
            "loose_name_matches": loose_cmp["name_matches"],
        })

    with (OUT / "phase3_prefix_detail.csv").open("w", newline="", encoding="utf-8") as f:
        if detail:
            w = csv.DictWriter(f, fieldnames=list(detail[0].keys()))
            w.writeheader()
            w.writerows(detail)

    # Aggregate suffix distribution of the strict best-pick per row (reflects
    # what a real matcher would select under the canonical rule).
    strict_best_suffix_by_L = defaultdict(Counter)
    strict_name_ok_suffix_by_L = defaultdict(Counter)
    for d in detail:
        if d["strict_suffix"]:
            strict_best_suffix_by_L[d["code_len"]][d["strict_suffix"]] += 1
            if d["strict_name_matches"]:
                strict_name_ok_suffix_by_L[d["code_len"]][d["strict_suffix"]] += 1

    summary = {
        "unmatched_rows": len(unmatched_rows),
        "strict_rule": {
            "rows_with_any_candidate": strict_any,
            "rows_with_ambiguous_multi_candidate": strict_ambig,
            "best_pick_suffix_per_code_length": {
                str(L): dict(c.most_common(10))
                for L, c in strict_best_suffix_by_L.items()
            },
            "best_pick_suffix_where_name_matches_per_code_length": {
                str(L): dict(c.most_common(10))
                for L, c in strict_name_ok_suffix_by_L.items()
            },
            "all_candidate_suffix_top30": [
                {"code_len": k[0], "suffix": k[1], "count": v}
                for k, v in sorted(strict_suffix.items(), key=lambda x: -x[1])[:30]
            ],
        },
        "loose_rule": {
            "rows_with_any_candidate": loose_any,
            "rows_with_ambiguous_multi_candidate": loose_ambig,
            "rows_where_loose_matches_but_strict_doesnt": loose_only_extra,
            "total_extra_candidates_vs_strict": loose_added_candidates,
            "all_candidate_suffix_top30": [
                {"code_len": k[0], "pn_len": k[1], "suffix": k[2], "count": v}
                for k, v in sorted(loose_suffix.items(), key=lambda x: -x[1])[:30]
            ],
        },
    }
    (OUT / "phase3_prefix.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False))
    return detail, summary


# ── Phase 4: false-positive analysis ────────────────────────────────────────


def phase4(phase3_detail):
    """
    A prefix match is a 'false positive' if the best prefix candidate's name
    clearly disagrees with the tasting wine's name. Analyze under both the
    strict and loose prefix rules, and cross-reference with producer:

      agree_both    name ok AND producer ok  - same wine
      cuvee_rename  name mismatch BUT producer ok  - likely label refresh
      wrong_pick    name ok BUT producer mismatch  - producer normalization
                    drift or we picked a sibling whose name happens to match
                    by coincidence
      real_fp       both mismatch  - the code prefix-matches an unrelated
                    wine; the code is stale / coincidental

    Publish the real_fp rows to phase4_false_positives.csv.
    """
    strict_rows = [d for d in phase3_detail if d["strict_n"] >= 1]
    # Confidence bands on strict name_sim
    bands_strict = {
        "ge_0.7": sum(1 for d in strict_rows if d["strict_name_sim"] >= 0.7),
        "0.4_to_0.7": sum(1 for d in strict_rows if 0.4 <= d["strict_name_sim"] < 0.7),
        "lt_0.4": sum(1 for d in strict_rows if d["strict_name_sim"] < 0.4),
    }

    strict_in_search = [d for d in strict_rows if d["strict_in_search"]]
    agree_both = sum(
        1 for d in strict_in_search
        if d["strict_name_matches"] and d["strict_producer_matches"]
    )
    name_no_prod = sum(
        1 for d in strict_in_search
        if d["strict_name_matches"] and not d["strict_producer_matches"]
    )
    prod_no_name = sum(
        1 for d in strict_in_search
        if (not d["strict_name_matches"]) and d["strict_producer_matches"]
    )
    neither = sum(
        1 for d in strict_in_search
        if not d["strict_name_matches"] and not d["strict_producer_matches"]
    )

    # Publish real FPs
    fps = [
        d for d in strict_in_search
        if not d["strict_name_matches"] and not d["strict_producer_matches"]
    ]
    with (OUT / "phase4_false_positives.csv").open("w", newline="", encoding="utf-8") as f:
        if fps:
            w = csv.DictWriter(f, fieldnames=list(fps[0].keys()))
            w.writeheader()
            w.writerows(fps)

    # Also report how much worse "loose" makes the false-positive picture.
    loose_rows = [d for d in phase3_detail if d["loose_n"] >= 1]
    loose_bands = {
        "ge_0.7": sum(1 for d in loose_rows if d["loose_name_sim"] >= 0.7),
        "0.4_to_0.7": sum(1 for d in loose_rows if 0.4 <= d["loose_name_sim"] < 0.7),
        "lt_0.4": sum(1 for d in loose_rows if d["loose_name_sim"] < 0.4),
    }

    summary = {
        "strict_rule": {
            "rows_with_prefix_candidate": len(strict_rows),
            "name_sim_bands": bands_strict,
            "in_search_rows": len(strict_in_search),
            "crosstab_name_vs_producer": {
                "name_ok_AND_producer_ok__same_wine": agree_both,
                "name_ok_BUT_producer_mismatch__wrong_pick_or_drift": name_no_prod,
                "producer_ok_BUT_name_mismatch__likely_cuvee_rename": prod_no_name,
                "both_mismatch__real_false_positive": neither,
            },
        },
        "loose_rule": {
            "rows_with_prefix_candidate": len(loose_rows),
            "name_sim_bands": loose_bands,
        },
    }
    (OUT / "phase4.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False))
    return summary


# ── Main ────────────────────────────────────────────────────────────────────


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    print("Loading tasting data...", file=sys.stderr)
    tasting = load_tasting_rows()
    print(f"  {len(tasting)} digit-code rows", file=sys.stderr)
    print("Loading catalog...", file=sys.stderr)
    cat_by_pn = load_catalog()
    print(f"  {len(cat_by_pn)} catalog items", file=sys.stderr)
    print("Loading search...", file=sys.stderr)
    search_by_pn = load_search()
    print(f"  {len(search_by_pn)} search wines", file=sys.stderr)

    print("Phase 1: exact-match analysis...", file=sys.stderr)
    p1_detail, p1_sum = phase1(tasting, cat_by_pn, search_by_pn)
    print(f"  buckets: {p1_sum['buckets']}", file=sys.stderr)

    print("Phase 2: collision analysis...", file=sys.stderr)
    p2_sum = phase2(p1_detail, tasting)

    print("Phase 3: prefix matching...", file=sys.stderr)
    p3_detail, p3_sum = phase3(tasting, cat_by_pn, search_by_pn)

    print("Phase 4: false-positive analysis...", file=sys.stderr)
    p4_sum = phase4(p3_detail)

    summary = {
        "phase1": p1_sum,
        "phase2": p2_sum,
        "phase3": p3_sum,
        "phase4": p4_sum,
    }
    (OUT / "summary.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False))
    print("Done. See product_code_analysis/out/", file=sys.stderr)


if __name__ == "__main__":
    main()
