#!/usr/bin/env python3
"""
Scrape past home sales from Booli's PUBLIC site into a CSV — no API key.

Drives a real Chromium (Playwright) past Cloudflare and harvests the sold
listings the site itself loads via GraphQL. See lib/booli_browser.py for how,
and api-docs/booli/PUBLIC_SITE.md for the constraints (notably: run from a
residential IP — Cloudflare loops forever on datacenter/VPN/proxy IPs).

Usage:
    pip install playwright && playwright install chromium

    # Give it the exact "slutpriser" URL you browse, e.g. for a kommun:
    python scrape_public.py --url "https://www.booli.se/slutpriser/nacka/76208/"
    python scrape_public.py --url "https://www.booli.se/slutpriser/stockholm/22/" \
        --max-pages 50 --out data/sthlm_sold.csv

    # Show the browser window (helps when first debugging the challenge):
    python scrape_public.py --url "..." --headful

    # Behind a TLS-terminating proxy (rarely needed at home):
    python scrape_public.py --url "..." --proxy http://127.0.0.1:8080
"""

from __future__ import annotations

import argparse
import csv
import sys

from lib.booli_browser import BooliBrowser, CloudflareBlocked
from lib.cache import data_path

# Columns flattened out of each intercepted sale object. The public GraphQL
# payload is richer and may nest differently than the Open API; we dig common
# paths and leave blanks for anything absent. Verify/extend against a live
# capture on your machine (see PUBLIC_SITE.md) before trusting the schema.
COLUMNS = [
    ("booliId", ("booliId",)),
    ("soldDate", ("soldDate",)),
    ("soldPrice", ("soldPrice", "raw")),
    ("listPrice", ("listPrice", "raw")),
    ("rooms", ("rooms", "formatted")),
    ("livingArea", ("livingArea", "raw")),
    ("objectType", ("objectType",)),
    ("streetAddress", ("streetAddress",)),
    ("municipality", ("descriptiveAreaName",)),
    ("latitude", ("latitude",)),
    ("longitude", ("longitude",)),
]


def _get_path(obj, path):
    cur = obj
    for key in path:
        if isinstance(cur, dict):
            cur = cur.get(key)
        else:
            return None
    # Some Booli scalar fields are wrapped as {"raw":.., "formatted":..}; if a
    # leaf is still such a dict, prefer its raw value.
    if isinstance(cur, dict) and "raw" in cur:
        return cur["raw"]
    return cur


def _flatten(sale):
    row = {name: _get_path(sale, path) for name, path in COLUMNS}
    # Fallbacks for the common flat shape.
    if row["soldPrice"] is None:
        row["soldPrice"] = sale.get("soldPrice")
    if row["streetAddress"] is None:
        row["streetAddress"] = sale.get("streetAddress")
    return row


def parse_args(argv=None):
    p = argparse.ArgumentParser(description="Scrape Booli public sold listings to CSV.")
    p.add_argument("--url", required=True,
                   help='a booli.se "/slutpriser/.../" URL (the one you browse)')
    p.add_argument("--max-pages", type=int, default=200)
    p.add_argument("--headful", action="store_true",
                   help="show the browser window (default: headless)")
    p.add_argument("--proxy", default=None, help="proxy server, if any")
    p.add_argument("--out", default=None, help="output CSV path")
    return p.parse_args(argv)


def default_out(url: str) -> str:
    slug = url.rstrip("/").split("/slutpriser/", 1)[-1].replace("/", "_") or "sold"
    return str(data_path(f"public_{slug}.csv"))


def main(argv=None) -> int:
    args = parse_args(argv)
    out_path = args.out or default_out(args.url)

    print(f"Scraping {args.url} (headless={not args.headful}) ...", file=sys.stderr)
    n = 0
    try:
        import os
        os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)
        with BooliBrowser(headless=not args.headful, proxy=args.proxy) as browser, \
                open(out_path, "w", newline="", encoding="utf-8") as fh:
            writer = csv.DictWriter(fh, fieldnames=[c[0] for c in COLUMNS])
            writer.writeheader()
            for sale in browser.iter_sold_url(args.url, max_pages=args.max_pages):
                writer.writerow(_flatten(sale))
                n += 1
                if n % 100 == 0:
                    print(f"  {n} sales...", file=sys.stderr)
    except CloudflareBlocked as e:
        print(f"\nBlocked: {e}", file=sys.stderr)
        print("Tip: run on your own (residential) connection, and try --headful "
              "once to watch the challenge.", file=sys.stderr)
        return 1
    except ImportError:
        print("Playwright is not installed. Run:\n"
              "  pip install playwright && playwright install chromium", file=sys.stderr)
        return 2

    print(f"Wrote {n} sales to {out_path}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
