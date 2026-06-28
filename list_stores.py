"""
list_stores.py  —  Cache the Systembolaget store network and resolve stores
from --postcode / --city / --name / --county filters.

Cache:
  cache/stores.json       — full /v1/sitesearch/site?q=  dump

Examples:
  # refresh the cache
  python3 list_stores.py --refresh

  # find stores by city
  python3 list_stores.py --city Stockholm

  # find stores by display-name substring
  python3 list_stores.py --name "Götgatan"

  # resolve a postcode to nearby stores (via postalCity + home-delivery depot)
  python3 list_stores.py --postcode 11454

  # print just the siteIds (pipe-friendly)
  python3 list_stores.py --city Stockholm --siteids-only

Sitesearch records have: siteId (zero-padded string), displayName,
streetAddress, city, county, isAgent, isBlocked, isTastingStore,
openingHours, position (lat/lon). postalCode is always null on this
endpoint — use /v1/postalCode/{code} (wrapped by lib.sb_api.fetch_postal_code)
to resolve a customer postcode to city + depot. isAgent=true are
third-party alcohol agents (C073).
"""

import argparse
import json
import sys
from pathlib import Path

from lib import cache as _c
from lib import sb_api


def load_stores():
    if not _c.STORES_PATH.exists():
        print(f"[list_stores] {_c.STORES_PATH} missing — run with --refresh first.",
              file=sys.stderr)
        sys.exit(2)
    return _c.read_json(_c.STORES_PATH).get("siteSearchResults", [])


def refresh_cache():
    s = sb_api.session()
    print("[list_stores] fetching /v1/sitesearch/site?q= ...", file=sys.stderr)
    body = sb_api.fetch_stores(s, q="")
    _c.write_json(_c.STORES_PATH, body)
    n = len(body.get("siteSearchResults", []))
    n_real = sum(1 for r in body.get("siteSearchResults", []) if not r.get("isAgent"))
    print(f"[list_stores] wrote {_c.STORES_PATH} ({n} sites, {n_real} real stores)",
          file=sys.stderr)


def resolve_postcode_to_city(postcode: str):
    """Use the live /v1/postalCode/{code} endpoint to translate a customer
    postcode into its postalCity (so we can match it against the store list,
    which does not carry postalCode itself). Returns None if the postcode
    isn't served."""
    s = sb_api.session()
    body = sb_api.fetch_postal_code(s, postcode)
    if not body:
        return None
    return body.get("postalCity")


def filter_stores(stores, *, postcode=None, city=None, name=None, county=None,
                  include_agents=False):
    resolved_city = city
    if postcode and not city:
        resolved_city = resolve_postcode_to_city(postcode)
        if resolved_city is None:
            print(f"[list_stores] postcode {postcode!r} not served (no delivery);"
                  " falling back to no-city filter.", file=sys.stderr)
    out = []
    for r in stores:
        if not include_agents and r.get("isAgent"):
            continue
        if resolved_city:
            if (r.get("city") or "").lower() != resolved_city.lower():
                continue
        if county:
            if county.lower() not in (r.get("county") or "").lower():
                continue
        if name:
            hay = " ".join([
                r.get("displayName") or "",
                r.get("streetAddress") or "",
                r.get("alias") or "",
            ]).lower()
            if name.lower() not in hay:
                continue
        out.append(r)
    return out


def resolve_store_ids(
    postcode=None, city=None, name=None, county=None, include_agents=False,
):
    """Importable helper: returns list of siteId strings matching the filters."""
    stores = load_stores()
    matched = filter_stores(
        stores,
        postcode=postcode, city=city, name=name, county=county,
        include_agents=include_agents,
    )
    return [r["siteId"] for r in matched]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--refresh", action="store_true",
                    help="refetch cache/stores.json from the API")
    ap.add_argument("--postcode",
                    help="resolve via /v1/postalCode/{code} to a postalCity")
    ap.add_argument("--city")
    ap.add_argument("--county")
    ap.add_argument("--name", help="substring of displayName/streetAddress")
    ap.add_argument("--include-agents", action="store_true",
                    help="include isAgent=true third-party alcohol agents")
    ap.add_argument("--siteids-only", action="store_true",
                    help="print only siteIds, one per line")
    ap.add_argument("--json", action="store_true",
                    help="print matched records as JSON lines")
    args = ap.parse_args()

    if args.refresh or not _c.STORES_PATH.exists():
        refresh_cache()
        if args.refresh and not any([args.postcode, args.city, args.county, args.name]):
            return

    matched = filter_stores(
        load_stores(),
        postcode=args.postcode,
        city=args.city,
        county=args.county,
        name=args.name,
        include_agents=args.include_agents,
    )

    if args.siteids_only:
        for r in matched:
            print(r["siteId"])
        return
    if args.json:
        for r in matched:
            print(json.dumps(r, ensure_ascii=False))
        return

    print(f"{len(matched)} store(s):", file=sys.stderr)
    for r in matched:
        print(f"  {r['siteId']}  {r.get('displayName','')}  "
              f"{r.get('streetAddress','')}, {r.get('city','')}  "
              f"({r.get('county','')})")


if __name__ == "__main__":
    main()
