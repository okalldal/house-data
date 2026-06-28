#!/usr/bin/env python3
"""
Scrape past home sales from Booli into a CSV.

Pipeline entry point. Resolves a region (kommun / area name or id), pages
through every matching sale on the Booli Open API `/sold` endpoint, and writes
a flat CSV to `data/sold_<region>.csv`.

Usage:
    export BOOLI_CALLER_ID=...    # request from api@booli.se (claim B004)
    export BOOLI_KEY=...
    python scrape_sold.py --area "Nacka"
    python scrape_sold.py --area-id 76208 --object-type Villa --min-sold-date 2020-01-01
    python scrape_sold.py --area "Stockholm" --max-records 5000 --out data/sthlm.csv

The data shape this writes follows claims B011–B015 in api-docs/booli/api.md
(PENDING until verified with a real key). Run the probes first to confirm:
    pytest api-docs/booli/tests/
"""

from __future__ import annotations

import argparse
import csv
import sys

from lib.booli_api import BooliClient, BooliError
from lib.cache import data_path

# Columns flattened out of each /sold record. Nested location fields are dug
# out by _get_path. Adjust here once the live schema is verified.
COLUMNS = [
    ("booliId", ("booliId",)),
    ("soldDate", ("soldDate",)),
    ("soldPrice", ("soldPrice",)),
    ("listPrice", ("listPrice",)),
    ("objectType", ("objectType",)),
    ("rooms", ("rooms",)),
    ("livingArea", ("livingArea",)),
    ("plotArea", ("plotArea",)),
    ("rent", ("rent",)),
    ("constructionYear", ("constructionYear",)),
    ("streetAddress", ("location", "address", "streetAddress")),
    ("city", ("location", "address", "city")),
    ("municipality", ("location", "region", "municipalityName")),
    ("county", ("location", "region", "countyName")),
    ("latitude", ("location", "position", "latitude")),
    ("longitude", ("location", "position", "longitude")),
]


def _get_path(obj, path):
    cur = obj
    for key in path:
        if not isinstance(cur, dict):
            return None
        cur = cur.get(key)
    return cur


def _flatten(record):
    return {name: _get_path(record, path) for name, path in COLUMNS}


def parse_args(argv=None):
    p = argparse.ArgumentParser(description="Scrape Booli past home sales to CSV.")
    region = p.add_mutually_exclusive_group(required=True)
    region.add_argument("--area", help="free-text place name (Booli q= param)")
    region.add_argument("--area-id", type=int, help="Booli areaId (see /areas)")
    p.add_argument("--object-type", help="e.g. Lägenhet, Villa, Radhus")
    p.add_argument("--min-sold-date", help="ISO date, inclusive lower bound")
    p.add_argument("--max-sold-date", help="ISO date, inclusive upper bound")
    p.add_argument("--max-records", type=int, default=None,
                   help="stop after N records (default: all)")
    p.add_argument("--page-size", type=int, default=100)
    p.add_argument("--out", help="output CSV path (default: data/sold_<region>.csv)")
    return p.parse_args(argv)


def build_filters(args) -> dict:
    filters: dict = {}
    if args.area_id is not None:
        filters["areaId"] = args.area_id
    else:
        filters["q"] = args.area
    if args.object_type:
        filters["objectType"] = args.object_type
    if args.min_sold_date:
        filters["minSoldDate"] = args.min_sold_date
    if args.max_sold_date:
        filters["maxSoldDate"] = args.max_sold_date
    return filters


def default_out(args) -> str:
    slug = str(args.area_id) if args.area_id is not None else \
        args.area.lower().replace(" ", "_")
    return str(data_path(f"sold_{slug}.csv"))


def main(argv=None) -> int:
    args = parse_args(argv)
    try:
        client = BooliClient.from_env()
    except ValueError as e:
        print(f"error: {e}\nSet BOOLI_CALLER_ID and BOOLI_KEY "
              f"(request an identity from api@booli.se).", file=sys.stderr)
        return 2

    filters = build_filters(args)
    out_path = args.out or default_out(args)

    print(f"Fetching sold homes for {filters} ...", file=sys.stderr)
    n = 0
    try:
        import os
        os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)
        with open(out_path, "w", newline="", encoding="utf-8") as fh:
            writer = csv.DictWriter(fh, fieldnames=[c[0] for c in COLUMNS])
            writer.writeheader()
            for record in client.iter_sold(page_size=args.page_size,
                                            max_records=args.max_records,
                                            **filters):
                writer.writerow(_flatten(record))
                n += 1
                if n % 500 == 0:
                    print(f"  {n} sales...", file=sys.stderr)
    except BooliError as e:
        print(f"Booli API error after {n} records: {e}", file=sys.stderr)
        if e.code == "FAILURE_IDENTITY_NOT_FOUND":
            print("Your callerId was not recognised — check BOOLI_CALLER_ID/KEY.",
                  file=sys.stderr)
        return 1

    print(f"Wrote {n} sales to {out_path}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
