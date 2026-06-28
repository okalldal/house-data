"""
match_wines.py  —  Build data/wines_matched.csv.

Joins Munskänkarna tasting rows (data/wines_clean.csv) to authoritative
Systembolaget productNumbers using lib.matching.match_row. Adds the
current productId, the current catalog name/producer/vintage/price/volume,
and a vintage_matches flag.

Drops rows that either have no Systembolaget id at all or whose match was
rejected (reason=no_match or reason=exact_name_mismatch). Low-confidence
sibling name-only matches are kept with their reason so downstream
scripts can choose to exclude them.
"""

import argparse
import csv
import json
import sys
from pathlib import Path

from lib import cache as _c
from lib import matching

DATA_CSV = _c.DATA_DIR / "wines_clean.csv"

OUTPUT_COLUMNS = [
    "tasting_row_id",
    "systembolaget_id",
    "tasting_name",
    "tasting_producer",
    "tasting_vintage",
    "points",
    "tasting_price",
    "tasting_volume",
    "country",
    "region",
    "activity_publish_date",
    "productNumber",
    "productId",
    "match_reason",
    "name_sim",
    "name_jaccard",
    "producer_sim",
    "vintage_matches",
    "sb_name",
    "sb_producer",
    "sb_vintage",
    "sb_price_sek",
    "sb_volume_ml",
    "sb_country",
    "sb_category",
    "sb_assortment",
]


def load_catalog_by_pn(path):
    cat = json.loads(Path(path).read_text())
    # Tasting codes should map to wine; restricting here prevents spurious
    # matches into Sprit/Öl/Cider prefix space.
    return {c["productNumber"]: c for c in cat if c.get("categoryLevel1") == "Vin"}


def load_search_by_pn(path):
    return {w["productNumber"]: w for w in json.loads(Path(path).read_text())}


def vintage_match_flag(tasting_year, sb_vintage):
    """Strict vintage comparison. Returns True/False/"" (unknown)."""
    if not tasting_year or str(tasting_year).strip() in ("", "0"):
        return ""  # tasting has no vintage to compare
    if sb_vintage in (None, ""):
        return ""  # catalog has no vintage (non-vintage wine)
    try:
        return int(str(sb_vintage)) == int(str(tasting_year))
    except (TypeError, ValueError):
        return ""


def run(args):
    catalog = load_catalog_by_pn(_c.CATALOG_PATH)
    search = load_search_by_pn(_c.WINE_SEARCH_PATH)
    print(f"[match] catalog={len(catalog)} wines, search={len(search)} wines",
          file=sys.stderr)

    _c.DATA_DIR.mkdir(parents=True, exist_ok=True)
    out_path = args.output or _c.WINES_MATCHED_CSV

    total = 0
    kept = 0
    reasons = {}
    with DATA_CSV.open(encoding="utf-8") as f_in, \
         open(out_path, "w", newline="", encoding="utf-8") as f_out:
        reader = csv.DictReader(f_in)
        writer = csv.DictWriter(f_out, fieldnames=OUTPUT_COLUMNS)
        writer.writeheader()

        for idx, row in enumerate(reader):
            total += 1
            sid = (row.get("systembolaget_id") or "").strip()
            if not sid or not sid.isdigit():
                continue
            tasting_row = {
                "code": sid,
                "name": row.get("name") or "",
                "producer": row.get("producer") or "",
                "year": (row.get("year") or "").strip(),
            }
            pn, reason, cmp = matching.match_row(tasting_row, catalog, search)
            reasons[reason] = reasons.get(reason, 0) + 1

            if not args.keep_all:
                if reason in ("no_match", "exact_name_mismatch"):
                    continue

            cat_hit = catalog.get(pn) if pn else None
            search_hit = search.get(pn) if pn else None
            pid = cat_hit["productId"] if cat_hit else ""

            sb_price = sb_volume = sb_country = sb_cat = sb_assort = ""
            if search_hit is not None:
                sb_price = search_hit.get("price") or ""
                sb_volume = search_hit.get("volume") or ""
                sb_country = search_hit.get("country") or ""
                sb_cat = search_hit.get("categoryLevel2") or ""
                sb_assort = search_hit.get("assortmentText") or ""

            points_raw = (row.get("points") or "").strip()
            try:
                points_val = float(points_raw) if points_raw else ""
            except ValueError:
                points_val = ""

            writer.writerow({
                "tasting_row_id": idx,
                "systembolaget_id": sid,
                "tasting_name": row.get("name") or "",
                "tasting_producer": row.get("producer") or "",
                "tasting_vintage": tasting_row["year"],
                "points": points_val,
                "tasting_price": (row.get("price") or "").strip(),
                "tasting_volume": (row.get("volume") or "").strip(),
                "country": row.get("country") or "",
                "region": row.get("region") or "",
                "activity_publish_date": row.get("activity_publish_date") or "",
                "productNumber": pn or "",
                "productId": pid,
                "match_reason": reason,
                "name_sim": cmp["name_sim"] if cmp else 0.0,
                "name_jaccard": cmp["name_jaccard"] if cmp else 0.0,
                "producer_sim": cmp["producer_sim"] if cmp else 0.0,
                "vintage_matches": vintage_match_flag(
                    tasting_row["year"], cmp["sb_vintage"] if cmp else None
                ),
                "sb_name": cmp["sb_name"] if cmp else "",
                "sb_producer": cmp["sb_producer"] if cmp else "",
                "sb_vintage": cmp["sb_vintage"] if cmp else "",
                "sb_price_sek": sb_price,
                "sb_volume_ml": sb_volume,
                "sb_country": sb_country,
                "sb_category": sb_cat,
                "sb_assortment": sb_assort,
            })
            kept += 1

    print(f"[match] read {total} rows, wrote {kept} to {out_path}",
          file=sys.stderr)
    print(f"[match] reasons: "
          f"{dict(sorted(reasons.items(), key=lambda x: -x[1]))}",
          file=sys.stderr)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--output", type=Path,
                    help=f"override output path (default {_c.WINES_MATCHED_CSV})")
    ap.add_argument("--keep-all", action="store_true",
                    help="also emit rows with no_match / exact_name_mismatch")
    args = ap.parse_args()
    run(args)


if __name__ == "__main__":
    main()
