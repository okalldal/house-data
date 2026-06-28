"""
build_catalog.py  —  Cache the Systembolaget catalog + full wine search index.

Writes:
  cache/catalog.json      — /v1/product dump (all SKUs, sparse index)
  cache/wine_search.json  — full wine search partitioned by country

Idempotent: skips when the target is fresher than --max-age-hours (default
24). Use --force to refetch unconditionally.
"""

import argparse
import sys

from lib import cache as _c
from lib import sb_api


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--force", action="store_true",
                    help="refetch even if cache is fresh")
    ap.add_argument("--max-age-hours", type=float, default=24.0,
                    help="cache is reused if younger than this (hours)")
    ap.add_argument("--skip-catalog", action="store_true")
    ap.add_argument("--skip-search", action="store_true")
    args = ap.parse_args()

    s = sb_api.session()

    if not args.skip_catalog:
        if args.force or not _c.is_fresh(_c.CATALOG_PATH, args.max_age_hours):
            print("[catalog] fetching /v1/product ...", file=sys.stderr)
            cat = sb_api.fetch_catalog(s)
            _c.write_json(_c.CATALOG_PATH, cat)
            print(f"[catalog] wrote {_c.CATALOG_PATH} ({len(cat)} items)", file=sys.stderr)
        else:
            print(f"[catalog] fresh ({_c.CATALOG_PATH}); skipping", file=sys.stderr)

    if not args.skip_search:
        if args.force or not _c.is_fresh(_c.WINE_SEARCH_PATH, args.max_age_hours):
            print("[search] paginating wine search per country ...", file=sys.stderr)

            def on_country(name, expected, collected, running):
                print(f"  {name}: collected {collected} "
                      f"(expected ~{expected}); total unique={running}",
                      file=sys.stderr)

            wines = sb_api.fetch_all_wines(s, on_country=on_country)
            _c.write_json(_c.WINE_SEARCH_PATH, wines)
            print(f"[search] wrote {_c.WINE_SEARCH_PATH} ({len(wines)} unique)",
                  file=sys.stderr)
        else:
            print(f"[search] fresh ({_c.WINE_SEARCH_PATH}); skipping", file=sys.stderr)


if __name__ == "__main__":
    main()
