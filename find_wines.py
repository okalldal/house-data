"""
find_wines.py  —  Rank Munskänkarna-rated wines that are actually buyable
at a given store, postcode, or as home delivery to a postcode.

Consumes:
  data/wines_matched.csv   (from match_wines.py)
  cache/stock/*.json.gz    (from refresh_stock.py)
  cache/wine_search.json   (current Systembolaget prices/vintages)
  cache/stores.json        (from list_stores.py)

Selection logic:
  1. Load wines_matched.csv, apply --min-points and the strict vintage
     rule (default: only rows where the current Systembolaget vintage
     equals the tasted vintage — per CLAUDE.md "different vintages =
     different wines").
  2. Resolve target stores from --store / --postcode / --city / --name.
     For --orderable-to-postcode the target is a depot.
  3. For each candidate wine, check stock at the target store(s) / depot.
     Wines that were not prefetched (points < prefetch threshold) can be
     filled on-demand with --on-demand.
  4. Attach current Systembolaget price/volume from wine_search.json
     (never from wines_clean.csv — see CLAUDE.md).
  5. Rank by --sort (points | value | price | volume) and print --top N.

Usage examples:

  # best wines at a specific store
  python3 find_wines.py --store 0163 --top 20

  # best wines orderable to your home (depot delivery)
  python3 find_wines.py --orderable-to-postcode 11454 --top 30

  # best wines in any central-Stockholm store
  python3 find_wines.py --postcode 11454 --top 30

  # best value (points per SEK per 750 ml)
  python3 find_wines.py --store 0163 --sort value --top 30

  # include wines with points 14-15 (below the prefetch threshold)
  # and fetch their stock on the fly for the target stores
  python3 find_wines.py --store 0163 --min-points 14 --on-demand
"""

import argparse
import csv
import sys

from lib import cache as _c
from lib import sb_api
import list_stores as list_stores_mod
import refresh_stock


def load_matched(min_points, strict_vintage, allow_name_only):
    rows = []
    with open(_c.WINES_MATCHED_CSV, encoding="utf-8") as f:
        for r in csv.DictReader(f):
            try:
                pts = float(r.get("points") or 0)
            except ValueError:
                continue
            if pts < min_points:
                continue
            reason = r.get("match_reason", "")
            if not allow_name_only and reason.endswith("_name_only"):
                continue
            if strict_vintage and r.get("vintage_matches") != "True":
                continue
            if not r.get("productId"):
                continue
            rows.append({**r, "points_float": pts})
    return rows


def resolve_target_stores(args, *, for_orderable=False):
    """Return list of siteIds (or depotIds) targeted by this query."""
    if for_orderable:
        s = sb_api.session()
        body = sb_api.fetch_postal_code(s, args.orderable_to_postcode)
        if not body or not body.get("homeOrderApplicable"):
            print(f"[find_wines] postcode {args.orderable_to_postcode!r} "
                  "is not served by home delivery.", file=sys.stderr)
            sys.exit(2)
        return [body["depotStockId"]], body
    sids = []
    if args.store:
        sids.extend(args.store)
    if args.postcode or args.city or args.name or args.county:
        sids.extend(list_stores_mod.resolve_store_ids(
            postcode=args.postcode, city=args.city,
            name=args.name, county=args.county,
        ))
    # dedup + preserve order
    seen = set()
    out = []
    for s in sids:
        if s not in seen:
            seen.add(s); out.append(s)
    return out, None


def read_stock(product_id):
    path = _c.stock_path(product_id)
    if not path.exists():
        return None
    try:
        return _c.read_json_gz(path)
    except Exception:
        return None


def in_store_stock(stock_cache, site_ids):
    """Return (total_stock, matched_entries). Entries include siteId info
    so we can show where each wine is stocked."""
    if not stock_cache:
        return 0, []
    total = 0
    hits = []
    wanted = set(site_ids)
    for e in stock_cache.get("storeStocks", []):
        st = e.get("store") or {}
        sb = e.get("stockBalance") or {}
        if st.get("siteId") in wanted:
            n = sb.get("stock") or 0
            total += n
            if n > 0:
                hits.append({
                    "siteId": st.get("siteId"),
                    "displayName": st.get("displayName") or st.get("alias"),
                    "city": st.get("city"),
                    "stock": n,
                    "shelf": sb.get("shelf"),
                })
    return total, hits


def in_depot_stock(stock_cache, depot_id):
    if not stock_cache:
        return 0
    return (stock_cache.get("depot_stock") or {}).get(depot_id, 0)


def current_api_data(product_number):
    """Look up the currently-listed price/vintage/volume from wine_search."""
    if not hasattr(current_api_data, "_idx"):
        data = _c.read_json(_c.WINE_SEARCH_PATH)
        current_api_data._idx = {w["productNumber"]: w for w in data}
    return current_api_data._idx.get(product_number)


def compute_sort_key(row, sort_by):
    pts = row["points_float"]
    price = float(row.get("sb_price_sek") or 0)
    volume = float(row.get("sb_volume_ml") or 0)
    if sort_by == "points":
        return (-pts, price)
    if sort_by == "price":
        return (price or 1e9, -pts)
    if sort_by == "volume":
        return (-volume, -pts)
    if sort_by == "value":
        # points / (price-per-750ml). Lower price-per-bottle → higher value.
        if price <= 0 or volume <= 0:
            return (float("inf"),)
        price_per_750 = price / volume * 750.0
        return (-(pts / price_per_750),)
    raise SystemExit(f"unknown --sort: {sort_by}")


def render_table(rows, sort_by):
    if not rows:
        print("(no wines matched)")
        return
    # Pick columns to show.
    print(f"{'Pts':>4}  {'Vin':>4}  {'Price':>6}  {'Vol':>5}  "
          f"{'Value':>5}  Name (producer) — where")
    for r in rows:
        pts = r["points_float"]
        vin = r.get("sb_vintage") or r.get("tasting_vintage") or ""
        price = r.get("sb_price_sek") or ""
        vol = r.get("sb_volume_ml") or ""
        try:
            p = float(price); v = float(vol)
            value = f"{pts / (p/v*750):.3f}" if p and v else ""
        except (TypeError, ValueError):
            value = ""
        name = (r.get("sb_name") or r.get("tasting_name") or "").strip()
        producer = (r.get("sb_producer") or r.get("tasting_producer") or "").strip()
        where = r.get("_where", "")
        print(f"{pts:>4}  {vin!s:>4}  {price!s:>6}  {vol!s:>5}  "
              f"{value!s:>5}  {name} ({producer}) — {where}")


def write_csv(rows, path):
    if not rows:
        return
    keys = ["points", "sb_vintage", "sb_name", "sb_producer",
            "sb_price_sek", "sb_volume_ml", "sb_country", "sb_category",
            "productNumber", "productId", "match_reason", "_where"]
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=keys)
        w.writeheader()
        for r in rows:
            w.writerow({
                "points": r["points_float"],
                **{k: r.get(k, "") for k in keys if k not in ("points",)},
            })


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    # target
    g = ap.add_argument_group("target")
    g.add_argument("--store", action="append", default=[],
                   help="siteId (repeatable)")
    g.add_argument("--postcode",
                   help="resolve to postalCity then match stores in that city")
    g.add_argument("--city")
    g.add_argument("--county")
    g.add_argument("--name", help="store display-name substring")
    g.add_argument("--orderable-to-postcode",
                   help="match wines orderable for home delivery to this postcode "
                        "(via depot stock)")
    # filters
    ap.add_argument("--min-points", type=float, default=14.0)
    ap.add_argument("--vintage-match", choices=("strict", "any"), default="strict")
    ap.add_argument("--allow-name-only", action="store_true",
                    help="include low-confidence sibling_*_name_only matches")
    # ranking / output
    ap.add_argument("--sort", choices=("points", "value", "price", "volume"),
                    default="points")
    ap.add_argument("--top", type=int, default=30)
    ap.add_argument("--csv", help="write full result to this CSV")
    # fetching
    ap.add_argument("--on-demand", action="store_true",
                    help="fetch stock on the fly for wines not in the cache")
    ap.add_argument("--sleep", type=float,
                    default=refresh_stock.DEFAULT_SLEEP_S)
    args = ap.parse_args()

    if not (args.store or args.postcode or args.city or args.name or
            args.county or args.orderable_to_postcode):
        ap.error("need at least one of --store / --postcode / --city / "
                 "--name / --county / --orderable-to-postcode")

    orderable = bool(args.orderable_to_postcode)
    targets, delivery_info = resolve_target_stores(args, for_orderable=orderable)
    if not targets:
        print("[find_wines] no target stores resolved.", file=sys.stderr)
        sys.exit(2)
    if orderable:
        print(f"[find_wines] depot {targets[0]} "
              f"(postcode {args.orderable_to_postcode} → "
              f"{delivery_info.get('postalCity')}), "
              f"first delivery {delivery_info.get('firstAvailableHomeDeliveryDate')}",
              file=sys.stderr)
    else:
        print(f"[find_wines] {len(targets)} target store(s): "
              f"{', '.join(targets)}", file=sys.stderr)

    candidates = load_matched(
        min_points=args.min_points,
        strict_vintage=(args.vintage_match == "strict"),
        allow_name_only=args.allow_name_only,
    )
    print(f"[find_wines] {len(candidates)} candidate wines "
          f"(min_points={args.min_points}, vintage_match={args.vintage_match})",
          file=sys.stderr)

    # For on-demand mode, identify cache misses first and fill them.
    if args.on_demand and not orderable:
        missing = [r["productId"] for r in candidates
                   if not _c.stock_path(r["productId"]).exists()]
        missing = list(dict.fromkeys(missing))  # dedup, preserve order
        if missing:
            print(f"[find_wines] on-demand: {len(missing)} products × "
                  f"{len(targets)} stores", file=sys.stderr)
            refresh_stock.on_demand_single_store(
                missing, targets, sleep_s=args.sleep,
            )
    if orderable:
        # Ensure every candidate's cache has depot stock for this depot.
        all_pids = list({r["productId"] for r in candidates})
        refresh_stock.refresh_depot_for_postcode(
            args.orderable_to_postcode, all_pids, sleep_s=args.sleep,
        )

    # Filter to what's in stock.
    picked = []
    for r in candidates:
        stock_cache = read_stock(r["productId"])
        if orderable:
            n = in_depot_stock(stock_cache, targets[0])
            if n <= 0:
                continue
            r["_where"] = f"depot {targets[0]} (stock={n})"
        else:
            total, hits = in_store_stock(stock_cache, targets)
            if total <= 0:
                continue
            shown = ", ".join(
                f"{h['displayName'] or h['siteId']} ({h['stock']})"
                for h in hits[:3]
            )
            if len(hits) > 3:
                shown += f", +{len(hits)-3} more"
            r["_where"] = shown

        # Refresh price/volume/vintage from wine_search (always current).
        cur = current_api_data(r["productNumber"])
        if cur is not None:
            r["sb_price_sek"] = cur.get("price") or r.get("sb_price_sek")
            r["sb_volume_ml"] = cur.get("volume") or r.get("sb_volume_ml")
            r["sb_vintage"] = cur.get("vintage") or r.get("sb_vintage")
            r["sb_name"] = ((cur.get("productNameBold") or "") + " "
                            + (cur.get("productNameThin") or "")).strip() or r.get("sb_name")
            r["sb_producer"] = cur.get("producerName") or r.get("sb_producer")
        picked.append(r)

    # Dedup by productNumber, keeping the highest-points tasting (multiple
    # tasting rows often map to the same SKU / vintage).
    best_by_pn = {}
    for r in picked:
        pn = r["productNumber"]
        if pn not in best_by_pn or r["points_float"] > best_by_pn[pn]["points_float"]:
            best_by_pn[pn] = r
    picked = list(best_by_pn.values())

    picked.sort(key=lambda r: compute_sort_key(r, args.sort))

    top = picked[: args.top]
    print(f"[find_wines] {len(picked)} wines available "
          f"(showing top {len(top)} by {args.sort})",
          file=sys.stderr)
    render_table(top, args.sort)
    if args.csv:
        write_csv(picked, args.csv)
        print(f"[find_wines] wrote full result to {args.csv}", file=sys.stderr)


if __name__ == "__main__":
    main()
