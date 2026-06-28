"""
match.py  -  Match Munskänkarna tasting rows to Systembolaget productNumbers.

Applies the verdict from ../product_code_analysis/findings.md:

  1. If the tasting code is itself a valid `productNumber` in the catalog,
     take it.
  2. Otherwise try sibling candidates `code + "01"`, then `"02"`, `"06"`,
     `"08"`, `"09"`, `"11"` (covers >99% of real matches per phase3).
  3. Accept a sibling candidate only under the two-signal rule
     (name similar AND producer similar). This rejects ~7,300 of the
     ~15,000 naive prefix matches that the prior analysis showed were
     reused codes pointing at unrelated wines.

Output rows carry the productNumber (and productId via catalog join),
the matched Systembolaget name/producer/vintage, and a short reason
code so downstream stages can segment by match quality.
"""

import csv
import json
import re
import sys
import unicodedata
from difflib import SequenceMatcher
from pathlib import Path

ROOT = Path(__file__).parent
DATA_CSV = ROOT.parent / "data" / "wines_clean.csv"
CATALOG = ROOT.parent / "product_code_analysis" / "cache" / "catalog.json"
SEARCH = ROOT.parent / "product_code_analysis" / "cache" / "wine_search.json"
OUT = ROOT / "out"

SIBLING_SUFFIXES = ("01", "02", "06", "08", "09", "11")

_WS_RE = re.compile(r"\s+")


def norm(s: str) -> str:
    if not s:
        return ""
    s = unicodedata.normalize("NFKD", s.strip().lower())
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = re.sub(r"[^\w\s]", " ", s)
    return _WS_RE.sub(" ", s).strip()


def name_sim(a: str, b: str) -> float:
    a, b = norm(a), norm(b)
    if not a or not b:
        return 0.0
    return SequenceMatcher(None, a, b).ratio()


def jaccard(a: str, b: str) -> float:
    ta, tb = set(norm(a).split()), set(norm(b).split())
    if not ta or not tb:
        return 0.0
    return len(ta & tb) / len(ta | tb)


def load_tastings():
    rows = []
    with DATA_CSV.open(encoding="utf-8") as f:
        for row in csv.DictReader(f):
            sid = (row.get("systembolaget_id") or "").strip()
            if not sid or not sid.isdigit():
                continue
            rows.append({
                "code": sid,
                "name": row.get("name") or "",
                "producer": row.get("producer") or "",
                "year": (row.get("year") or "").strip(),
                "activity_name": row.get("activity_name") or "",
                "activity_date": row.get("activity_publish_date") or "",
            })
    return rows


def load_catalog():
    cat = json.loads(CATALOG.read_text())
    # Restrict to wine items. Tasting codes ought to map to wine; limiting
    # here prevents collisions with Sprit / Öl / Cider prefixes.
    return {c["productNumber"]: c for c in cat if c.get("categoryLevel1") == "Vin"}


def load_search():
    return {w["productNumber"]: w for w in json.loads(SEARCH.read_text())}


def compare(row, search_hit, catalog_hit):
    sb_name_bold = ""
    sb_name = ""
    sb_producer = ""
    sb_vintage = None
    in_search = search_hit is not None
    if search_hit is not None:
        sb_name_bold = search_hit.get("productNameBold") or ""
        thin = search_hit.get("productNameThin") or ""
        sb_name = (sb_name_bold + " " + thin).strip()
        sb_producer = search_hit.get("producerName") or ""
        sb_vintage = search_hit.get("vintage")
    elif catalog_hit is not None:
        sb_name_bold = catalog_hit.get("productNameBold") or ""
        sb_name = sb_name_bold

    sim = name_sim(row["name"], sb_name)
    jac = jaccard(row["name"], sb_name)
    prod_sim = name_sim(row["producer"], sb_producer) if sb_producer else 0.0

    return {
        "in_search": in_search,
        "sb_name": sb_name,
        "sb_producer": sb_producer,
        "sb_vintage": sb_vintage,
        "name_sim": round(sim, 3),
        "name_jaccard": round(jac, 3),
        "producer_sim": round(prod_sim, 3),
        "name_ok": sim >= 0.6 or jac >= 0.5,
        "producer_ok": prod_sim >= 0.6,
    }


def match_row(row, catalog_by_pn, search_by_pn):
    """
    Pick the best productNumber for a tasting row. Returns
    (productNumber, reason, cmp_dict). Reason values:
      exact                  code is a valid productNumber; name agrees
      exact_name_mismatch    code is a valid productNumber but name/producer
                             do NOT agree (code collision; likely recycled)
      sibling_<ss>           code + <ss> is valid AND name+producer agree
      sibling_name_only      sibling candidate exists, name agrees but
                             producer doesn't (low-confidence match)
      no_match               code not in catalog and no sibling agrees
    """
    code = row["code"]

    # Exact match against productNumber.
    if code in catalog_by_pn or code in search_by_pn:
        cmp = compare(row, search_by_pn.get(code), catalog_by_pn.get(code))
        if cmp["name_ok"] and (cmp["producer_ok"] or not cmp["sb_producer"]):
            return code, "exact", cmp
        # Exact but names disagree - the PN has been recycled, or was never
        # the same wine (4-5 digit codes can coincide with short-PN spirits).
        return code, "exact_name_mismatch", cmp

    # Try sibling suffixes. Prefer the first suffix that passes two-signal
    # agreement. Within suffixes we test in priority order because real
    # matches concentrate on `01` (96% per phase3 name-matching subset).
    fallback = None
    for suf in SIBLING_SUFFIXES:
        candidate = code + suf
        if candidate not in catalog_by_pn:
            continue
        cmp = compare(row, search_by_pn.get(candidate), catalog_by_pn.get(candidate))
        if cmp["name_ok"] and cmp["producer_ok"]:
            return candidate, f"sibling_{suf}", cmp
        # Keep the first name-only match as a soft fallback, but do NOT
        # return it unless nothing stronger shows up.
        if fallback is None and cmp["name_ok"]:
            fallback = (candidate, f"sibling_{suf}_name_only", cmp)

    if fallback is not None:
        return fallback

    return None, "no_match", None


def tasting_year(row):
    """Year of the tasting session, not of the wine."""
    d = row.get("activity_date") or ""
    return d[:4] if d[:4].isdigit() else ""


def run():
    OUT.mkdir(parents=True, exist_ok=True)
    tastings = load_tastings()
    catalog = load_catalog()
    search = load_search()
    print(f"[match] {len(tastings)} tasting rows, "
          f"{len(catalog)} catalog wines, {len(search)} search wines",
          file=sys.stderr)

    rows_out = []
    reasons = {}
    needed_productIds = set()

    for r in tastings:
        pn, reason, cmp = match_row(r, catalog, search)
        reasons[reason] = reasons.get(reason, 0) + 1
        cat_hit = catalog.get(pn) if pn else None
        pid = cat_hit["productId"] if cat_hit else ""
        row = {
            "code": r["code"],
            "tasting_name": r["name"],
            "tasting_producer": r["producer"],
            "tasting_wine_year": r["year"],
            "tasting_year": tasting_year(r),
            "activity_date": r["activity_date"],
            "matched_pn": pn or "",
            "matched_productId": pid,
            "match_reason": reason,
            "sb_name": cmp["sb_name"] if cmp else "",
            "sb_producer": cmp["sb_producer"] if cmp else "",
            "sb_vintage": cmp["sb_vintage"] if cmp else "",
            "name_sim": cmp["name_sim"] if cmp else 0.0,
            "name_jaccard": cmp["name_jaccard"] if cmp else 0.0,
            "producer_sim": cmp["producer_sim"] if cmp else 0.0,
            "in_search": cmp["in_search"] if cmp else False,
        }
        # Vintage verdict: only meaningful when both sides have a vintage.
        tv = r["year"]
        sv = cmp["sb_vintage"] if cmp else None
        if pn and tv and sv is not None and str(sv).isdigit() and tv.isdigit():
            row["vintage_matches"] = int(sv) == int(tv)
        elif pn and not tv:
            row["vintage_matches"] = "no_tasting_year"
        elif pn and sv in (None, ""):
            row["vintage_matches"] = "no_sb_vintage"
        else:
            row["vintage_matches"] = ""
        rows_out.append(row)

        # Collect productIds for rows that pass the "identity + vintage"
        # bar. Stock-fetching is expensive so we only query where it can
        # change the classification.
        strong_match = (
            reason.startswith(("exact", "sibling_"))
            and not reason.endswith("_name_only")
            and reason != "exact_name_mismatch"
        )
        vintage_ok = row["vintage_matches"] is True or row["vintage_matches"] == "no_sb_vintage"
        if pid and strong_match and vintage_ok:
            needed_productIds.add(pid)

    # Write detail CSV.
    with (OUT / "match_detail.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows_out[0].keys()))
        w.writeheader()
        w.writerows(rows_out)

    # Write summary + needed product ids.
    summary = {
        "tasting_rows": len(tastings),
        "match_reasons": dict(sorted(reasons.items(), key=lambda x: -x[1])),
        "rows_with_pn": sum(1 for r in rows_out if r["matched_pn"]),
        "rows_with_vintage_match": sum(1 for r in rows_out if r["vintage_matches"] is True),
        "needed_productIds": len(needed_productIds),
    }
    (OUT / "match_summary.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False))
    (OUT / "needed_productIds.json").write_text(json.dumps(sorted(needed_productIds)))
    print(f"[match] match_reasons={summary['match_reasons']}", file=sys.stderr)
    print(f"[match] rows with PN={summary['rows_with_pn']}, "
          f"vintage match={summary['rows_with_vintage_match']}, "
          f"productIds to query={summary['needed_productIds']}",
          file=sys.stderr)


if __name__ == "__main__":
    run()
