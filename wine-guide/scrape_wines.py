"""
scrape_wines.py  –  Pull the full Munskänkarna Vinlocus tasting-note dataset.

One request to the `listwinebottles/` surface controller with an oversized
`pageSize` returns the entire historical archive — tens of thousands of rows,
every session, in a single JSON response. No pagination, no session
enumeration, no batching. See api-docs/munskankarna/api.md claims M031/M032.

Writes data/wines.csv with one row per tasting note (a wine published to
multiple sessions produces one row per session — this matches the baseline
scrape). Downstream cleaning lives in clean_wines.py.
"""

import csv
import sys
import requests

API_URL = "https://www.munskankarna.se/umbraco/surface/winesearch/listwinebottles/"
OUTPUT_PATH = "data/wines.csv"

# Larger than the corpus. The server has no observed upper cap on pageSize
# (verified by api-docs/munskankarna/tests/test_listwinebottles.py::test_M032),
# so one request returns everything.
PAGE_SIZE = 100000

COLUMNS = [
    "name", "year", "category", "country", "country_alias",
    "region", "sub_region", "producer", "importer", "price", "volume",
    "alcohol", "sugar_content", "points", "rate_text", "rate_is_typical",
    "rate_can_be_stored", "rate_category_symbol", "raw_materials",
    "systembolaget_id", "systembolaget_url",
    "activity_name", "activity_publish_date", "activity_url", "wine_url",
]


def flatten(item):
    link = item.get("wineBottleExternalLink") or {}
    return {
        "name":                  item.get("wineBottleName"),
        "year":                  item.get("wineBottleYearName"),
        "category":              item.get("wineBottleCategoryName"),
        "country":               item.get("wineBottleCountryName"),
        "country_alias":         item.get("wineBottleCountryAlias"),
        "region":                item.get("wineBottleRegionName"),
        "sub_region":            item.get("wineBottleSubRegionName"),
        "producer":              item.get("wineBottleProducerName"),
        "importer":              item.get("wineBottleImporter"),
        "price":                 item.get("wineBottlePrice"),
        "volume":                item.get("wineBottleVolume"),
        "alcohol":               item.get("wineBottleAlcohol"),
        "sugar_content":         item.get("wineBottleSugarContent"),
        "points":                item.get("wineBottleRatePoints"),
        "rate_text":             item.get("wineBottleRateText"),
        "rate_is_typical":       item.get("wineBottleRateIsTypical"),
        "rate_can_be_stored":    item.get("wineBottleRateCanBeStored"),
        "rate_category_symbol":  item.get("wineBottleRateCategorySymbol"),
        "raw_materials":         item.get("wineBottleRawMaterials"),
        "systembolaget_id":      link.get("text"),
        "systembolaget_url":     link.get("link"),
        "activity_name":         item.get("wineBottleActivityName"),
        "activity_publish_date": item.get("wineBottleActivityPublishDate"),
        "activity_url":          item.get("wineBottleActivityUrl"),
        "wine_url":              item.get("wineBottleUrl"),
    }


def main():
    s = requests.Session()
    s.headers["User-Agent"] = "Mozilla/5.0 (wine-guide research scraper; polite)"

    print(f"Fetching full Vinlocus archive (pageSize={PAGE_SIZE})...", file=sys.stderr)
    resp = s.post(
        API_URL,
        data={"pageIndex": 0, "pageSize": PAGE_SIZE, "sortOrder": ""},
        timeout=300,
    )
    resp.raise_for_status()
    body = resp.json()

    rows = body["result"]
    total = body["total"]
    if len(rows) != total:
        sys.exit(
            f"Short read: server reported total={total}, got {len(rows)} rows. "
            f"Increase PAGE_SIZE."
        )

    with open(OUTPUT_PATH, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=COLUMNS)
        writer.writeheader()
        writer.writerows(flatten(item) for item in rows)

    print(f"Wrote {total} wines to {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
