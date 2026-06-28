"""
analyze.py  -  Classify each tasting row by current availability and
aggregate by tasting year.

Reads:
  out/match_detail.csv           (from match.py)
  cache/stock_by_productId.json  (from fetch_stock.py)

Writes:
  out/availability_detail.csv    one row per tasting row with its verdict
  out/availability_by_year.csv   share of each verdict within each tasting year
  out/availability_summary.json  top-line numbers
  out/cutoff_table.csv           cumulative-through-year view for picking a cutoff

Classification (mutually exclusive, in priority order):

  no_match                 tasting code doesn't resolve to any wine
  code_recycled            exact productNumber match, but name/producer
                           disagree - the PN was reassigned
  weak_name_only           sibling match with name agreement only (no
                           producer confirmation); low confidence
  no_tasting_year          row has no recorded year, can't test vintage
  no_sb_vintage            matched, but SB listing has no vintage (NV
                           champagne, port, etc.) - special-cased below
  different_vintage        matched, but SB currently sells a different
                           vintage (the tasted one is not on shelf)
  listed_but_no_stock      matched + same vintage, but 0 stock anywhere
  available_depot_only     matched + same vintage + home-delivery only
  available_in_store       matched + same vintage + at least one store

Rows classified as `available_*` are the KEEPERS. Everything else is a
candidate for deletion.
"""

import csv
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).parent
OUT = ROOT / "out"
CACHE = ROOT / "cache"
DETAIL = OUT / "match_detail.csv"
STOCK = CACHE / "stock_by_productId.json"


def load_match_detail():
    with DETAIL.open(encoding="utf-8") as f:
        return list(csv.DictReader(f))


def classify(row, stock_cache):
    reason = row["match_reason"]
    vm = row["vintage_matches"]
    pid = row["matched_productId"]

    if reason == "no_match":
        return "no_match"
    if reason == "exact_name_mismatch":
        return "code_recycled"
    if reason.endswith("_name_only"):
        return "weak_name_only"

    if vm == "no_tasting_year":
        return "no_tasting_year"
    if vm == "no_sb_vintage":
        # Non-vintage wines (Champagne, port) that still list and sell
        # are legitimately available; we bucket them separately so the
        # caller can choose how to treat them.
        if pid in stock_cache:
            st = stock_cache[pid]
            if st["store_total"] > 0:
                return "available_in_store_nv"
            if st["depot_total"] > 0:
                return "available_depot_only_nv"
            return "listed_but_no_stock_nv"
        return "listed_nv_not_queried"
    if vm == "False" or vm is False:
        return "different_vintage"
    # vm == True / "True"
    if pid not in stock_cache:
        return "match_but_no_stock_data"
    st = stock_cache[pid]
    if st["store_total"] > 0:
        return "available_in_store"
    if st["depot_total"] > 0:
        return "available_depot_only"
    return "listed_but_no_stock"


AVAILABLE_BUCKETS = {
    "available_in_store",
    "available_depot_only",
    "available_in_store_nv",
    "available_depot_only_nv",
}
KEEP_BUCKETS = AVAILABLE_BUCKETS  # alias for clarity
DISCARD_BUCKETS = {
    "no_match",
    "code_recycled",
    "weak_name_only",
    "different_vintage",
    "listed_but_no_stock",
    "listed_but_no_stock_nv",
}


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    detail = load_match_detail()
    stock_cache = json.loads(STOCK.read_text()) if STOCK.exists() else {}
    if not stock_cache:
        print("[warn] stock cache is empty - run fetch_stock.py first",
              file=sys.stderr)

    # Normalise vintage_matches string into real bool where applicable.
    for r in detail:
        if r["vintage_matches"] == "True":
            r["vintage_matches"] = True
        elif r["vintage_matches"] == "False":
            r["vintage_matches"] = False

    # Classify
    out_rows = []
    by_verdict = Counter()
    by_year = defaultdict(Counter)
    for r in detail:
        v = classify(r, stock_cache)
        pid = r["matched_productId"]
        st = stock_cache.get(pid) or {}
        out_rows.append({
            **r,
            "verdict": v,
            "store_total": st.get("store_total", ""),
            "stores_with_stock": st.get("stores_with_stock", ""),
            "depot_total": st.get("depot_total", ""),
        })
        by_verdict[v] += 1
        by_year[r["tasting_year"] or "unknown"][v] += 1

    # Detail CSV
    with (OUT / "availability_detail.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(out_rows[0].keys()))
        w.writeheader()
        w.writerows(out_rows)

    # Per-year table.
    verdicts_sorted = sorted(by_verdict.keys())
    year_rows = []
    for year in sorted(by_year.keys()):
        counts = by_year[year]
        total = sum(counts.values())
        keep = sum(counts[v] for v in KEEP_BUCKETS)
        row = {"tasting_year": year, "total": total,
               "keep": keep, "keep_pct": round(100 * keep / total, 1) if total else 0.0}
        for v in verdicts_sorted:
            row[v] = counts.get(v, 0)
        year_rows.append(row)
    with (OUT / "availability_by_year.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(year_rows[0].keys()))
        w.writeheader()
        w.writerows(year_rows)

    # Cutoff table: for each candidate cutoff year, what does the kept
    # dataset look like if we DROP everything published strictly before.
    # This is the decision-support view for "can we throw away pre-YEAR
    # tastings without losing much?".
    year_rows_sorted = [r for r in year_rows if r["tasting_year"].isdigit()]
    year_rows_sorted.sort(key=lambda r: r["tasting_year"])
    total_all = sum(r["total"] for r in year_rows_sorted)
    total_keep = sum(r["keep"] for r in year_rows_sorted)
    cutoff_rows = []
    cum_drop = 0
    cum_lost_keeps = 0
    for r in year_rows_sorted:
        cutoff_rows.append({
            "cutoff_year": r["tasting_year"],
            "rows_dropped_before_cutoff": cum_drop,
            "keepers_lost_before_cutoff": cum_lost_keeps,
            "rows_remaining": total_all - cum_drop,
            "keepers_remaining": total_keep - cum_lost_keeps,
            "share_of_dropped_that_were_keepers":
                round(100 * cum_lost_keeps / cum_drop, 2) if cum_drop else 0.0,
            "share_of_keepers_lost":
                round(100 * cum_lost_keeps / total_keep, 2) if total_keep else 0.0,
        })
        cum_drop += r["total"]
        cum_lost_keeps += r["keep"]
    with (OUT / "cutoff_table.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(cutoff_rows[0].keys()))
        w.writeheader()
        w.writerows(cutoff_rows)

    # Summary
    summary = {
        "total_tasting_rows": sum(by_verdict.values()),
        "verdicts": dict(by_verdict.most_common()),
        "keepers": sum(by_verdict[v] for v in KEEP_BUCKETS),
        "discards": sum(by_verdict[v] for v in DISCARD_BUCKETS),
        "keepers_pct": round(
            100 * sum(by_verdict[v] for v in KEEP_BUCKETS) / max(1, sum(by_verdict.values())),
            2,
        ),
        "productIds_with_stock_data": len(stock_cache),
    }
    (OUT / "availability_summary.json").write_text(
        json.dumps(summary, indent=2, ensure_ascii=False))
    print(json.dumps(summary, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
