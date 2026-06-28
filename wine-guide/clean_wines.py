"""
clean_wines.py  –  Deterministic cleaning for the Munskänkarna Vinlocus dataset.

Reads wines.csv, applies the rules below, writes wines_clean.csv and prints a
change summary.  Safe to re-run on any future scrape: every rule is either
purely additive (new columns), conservative (flag rather than overwrite), or
based on invariants of the API schema (price format, scoring scale, etc.).

Rules applied
─────────────
price         Strip Swedish thousands-separator commas ('1,049' → 1049).
              Zero-price kept as NULL (wines from private cellars at theme
              tastings – valid data, just not a retail price).
alcohol       Zero → NULL. 15 % of rows, concentrated in 2008–2012 sessions
              where the field wasn't recorded. Flagged rather than silently
              nulled so future truly-zero-alcohol wines surface for review.
year          Four-digit years 1900–current are kept as-is. '0' (non-vintage)
              is kept. Anything else (truncated entries like '202', '13') is
              moved to year_raw and year is set NULL so downstream code doesn't
              treat them as valid integers.
points        Values below 9 or above 20 moved to points_raw, points set NULL.
              Non-0.5-increment values (9.9, 16.6) also flagged.
systembolaget_id  'Nätvin' → NULL (placeholder used for online-only wines, not
              a real Systembolaget article number). Kept in systembolaget_id_raw.
grapes        raw_materials JSON re-emitted with grape names normalised via
              GRAPE_SYNONYMS table (e.g. 'shiraz'→'syrah', 'garnacha'→'grenache').
              Original kept in raw_materials_original. Synonym map is a plain
              dict at the top of this file – add entries as new variants appear.
"""

import csv
import json
import re
import sys
from datetime import date

INPUT_FILE  = "data/wines.csv"
OUTPUT_FILE = "data/wines_clean.csv"

# ── Grape synonym table ───────────────────────────────────────────────────────
# Maps non-canonical name → canonical name.
# Canonical = the most common spelling found in the dataset.
GRAPE_SYNONYMS = {
    # Same grape, different language
    "shiraz":            "syrah",
    "garnacha":          "grenache",
    "pinot nero":        "pinot noir",
    "pinot grigio":      "pinot gris",
    "pinot bianco":      "pinot blanc",
    "spätburgunder":     "pinot noir",
    "grauburgunder":     "pinot gris",
    "weißburgunder":     "pinot blanc",
    "blauburgunder":     "pinot noir",
    "brunello":          "sangiovese",
    "morellino":         "sangiovese",
    "prugnolo gentile":  "sangiovese",
    "tinta roriz":       "tempranillo",
    "aragonez":          "tempranillo",
    "tinta del pais":    "tempranillo",
    "ull de llebre":     "tempranillo",
    "cencibel":          "tempranillo",
    "monastrell":        "mourvèdre",
    "mataro":            "mourvèdre",
    "touriga nacional":  "touriga nacional",   # keep; just normalise accent
    "alvarinho":         "albariño",
    "malvasia fina":     "malvasia",
    "malvoisie":         "malvasia",
    "uva di troia":      "nero di troia",
}

CURRENT_YEAR = date.today().year


def clean_price(raw: str):
    """'1,049' → 1049  |  '169' → 169  |  '0' / '' → None"""
    if not raw:
        return None, False
    # Swedish thousands separator: digit-comma-digit where comma is NOT decimal
    cleaned = re.sub(r"(\d),(\d{3})$", r"\1\2", raw.strip())
    try:
        val = float(cleaned)
    except ValueError:
        return None, True   # unparseable → flag
    if val == 0:
        return None, False  # zero price = private-cellar wine, not a retail price
    return val, False


def clean_alcohol(raw: str):
    """0.0 → None (missing, not truly zero-alcohol). Flag so it's visible."""
    if not raw:
        return None, False
    try:
        val = float(raw)
    except ValueError:
        return None, True
    if val == 0:
        return None, True   # flagged: was '0', likely missing not zero-alcohol
    return val, False


def clean_year(raw: str):
    """
    Valid: 4-digit 1900–current, or '0' (non-vintage).
    Invalid: truncated ('202', '13'), garbage ('329').
    Returns (cleaned_value, is_bad).
    """
    if not raw:
        return None, False
    if raw == "0":
        return 0, False
    if re.fullmatch(r"\d{4}", raw):
        yr = int(raw)
        if 1900 <= yr <= CURRENT_YEAR:
            return yr, False
    return None, True   # truncated or out-of-range


def clean_points(raw: str):
    """
    Valid range: 9–20 in 0.5 increments.
    Returns (cleaned_float, is_out_of_range, is_bad_increment).
    """
    if not raw:
        return None, False, False
    try:
        val = float(raw)
    except ValueError:
        return None, True, False
    out_of_range    = not (9.0 <= val <= 20.0)
    bad_increment   = (round(val * 2) != val * 2)   # not a multiple of 0.5
    return val, out_of_range, bad_increment


def normalise_grapes(raw_materials_str: str):
    """Return (normalised_json_str, n_changes)."""
    if not raw_materials_str:
        return raw_materials_str, 0
    try:
        grapes = json.loads(raw_materials_str)
    except json.JSONDecodeError:
        return raw_materials_str, 0
    changes = 0
    for g in grapes:
        name = g.get("name", "").lower().strip()
        if name in GRAPE_SYNONYMS:
            g["name"] = GRAPE_SYNONYMS[name]
            changes += 1
        else:
            g["name"] = name   # normalise case regardless
    return json.dumps(grapes, ensure_ascii=False), changes


# ── Column schema for output ──────────────────────────────────────────────────
OUTPUT_COLUMNS = [
    # Core identity
    "name", "year", "category", "country", "country_alias",
    "region", "sub_region", "producer", "importer",
    # Retail
    "price", "volume", "alcohol", "sugar_content",
    # Assessment
    "points", "rate_text", "rate_is_typical", "rate_can_be_stored",
    "rate_category_symbol",
    # Grapes
    "raw_materials",
    # Links
    "systembolaget_id", "systembolaget_url",
    # Session
    "activity_name", "activity_publish_date", "activity_url", "wine_url",
    # Quality flags (True = value was suspect / changed)
    "flag_alcohol_zero",
    "flag_year_bad",
    "flag_points_out_of_range",
    "flag_points_bad_increment",
    "flag_systembolaget_placeholder",
    "flag_price_unparseable",
    # Originals preserved when a value was changed
    "year_raw",
    "points_raw",
    "systembolaget_id_raw",
    "raw_materials_original",
]


def main():
    counters = {
        "price_comma_fixed":       0,
        "price_zero_nulled":       0,
        "price_unparseable":       0,
        "alcohol_zero_flagged":    0,
        "year_bad_flagged":        0,
        "points_out_of_range":     0,
        "points_bad_increment":    0,
        "sb_placeholder_flagged":  0,
        "grape_names_normalised":  0,
    }

    with open(INPUT_FILE, encoding="utf-8") as fin, \
         open(OUTPUT_FILE, "w", newline="", encoding="utf-8") as fout:

        reader = csv.DictReader(fin)
        writer = csv.DictWriter(fout, fieldnames=OUTPUT_COLUMNS)
        writer.writeheader()

        for row in reader:
            out = {col: "" for col in OUTPUT_COLUMNS}

            # ── Pass-through fields ──────────────────────────────────────────
            for col in ("name", "category", "country", "country_alias",
                        "region", "sub_region", "producer", "importer",
                        "volume", "sugar_content", "rate_text",
                        "rate_is_typical", "rate_can_be_stored",
                        "rate_category_symbol", "systembolaget_url",
                        "activity_name", "activity_publish_date",
                        "activity_url", "wine_url"):
                out[col] = row.get(col, "")

            # ── Price ────────────────────────────────────────────────────────
            raw_price = row.get("price", "")
            if raw_price and "," in raw_price:
                counters["price_comma_fixed"] += 1
            price_val, price_bad = clean_price(raw_price)
            if price_bad:
                counters["price_unparseable"] += 1
                out["flag_price_unparseable"] = "True"
            if raw_price == "0":
                counters["price_zero_nulled"] += 1
            out["price"] = "" if price_val is None else price_val

            # ── Alcohol ──────────────────────────────────────────────────────
            alc_val, alc_flagged = clean_alcohol(row.get("alcohol", ""))
            out["alcohol"] = "" if alc_val is None else alc_val
            if alc_flagged:
                counters["alcohol_zero_flagged"] += 1
                out["flag_alcohol_zero"] = "True"

            # ── Year ─────────────────────────────────────────────────────────
            year_val, year_bad = clean_year(row.get("year", ""))
            if year_bad:
                counters["year_bad_flagged"] += 1
                out["flag_year_bad"]  = "True"
                out["year_raw"]       = row["year"]
                out["year"]           = ""
            else:
                out["year"] = "" if year_val is None else year_val

            # ── Points ───────────────────────────────────────────────────────
            pts_val, pts_oor, pts_bad_inc = clean_points(row.get("points", ""))
            if pts_oor or pts_bad_inc:
                if pts_oor:   counters["points_out_of_range"]   += 1
                if pts_bad_inc: counters["points_bad_increment"] += 1
                out["flag_points_out_of_range"]  = "True" if pts_oor    else ""
                out["flag_points_bad_increment"] = "True" if pts_bad_inc else ""
                out["points_raw"] = row["points"]
                out["points"]     = ""
            else:
                out["points"] = "" if pts_val is None else pts_val

            # ── Systembolaget ID ─────────────────────────────────────────────
            sb_id = row.get("systembolaget_id", "")
            if sb_id == "Nätvin":
                counters["sb_placeholder_flagged"] += 1
                out["flag_systembolaget_placeholder"] = "True"
                out["systembolaget_id_raw"] = sb_id
                out["systembolaget_id"]     = ""
            else:
                out["systembolaget_id"] = sb_id

            # ── Grapes ───────────────────────────────────────────────────────
            rm = row.get("raw_materials", "")
            normalised, n_changes = normalise_grapes(rm)
            if n_changes:
                counters["grape_names_normalised"] += n_changes
                out["raw_materials_original"] = rm
            out["raw_materials"] = normalised

            writer.writerow(out)

    # ── Summary ──────────────────────────────────────────────────────────────
    print(f"Wrote {OUTPUT_FILE}\n")
    print("── Change summary ──────────────────────────────────")
    labels = {
        "price_comma_fixed":       "Prices: thousands-comma stripped",
        "price_zero_nulled":       "Prices: zero → NULL (private-cellar wines)",
        "price_unparseable":       "Prices: unparseable → NULL + flagged",
        "alcohol_zero_flagged":    "Alcohol: zero → NULL + flagged",
        "year_bad_flagged":        "Years: truncated/invalid → NULL + flagged",
        "points_out_of_range":     "Points: outside 9–20 → NULL + flagged",
        "points_bad_increment":    "Points: non-0.5 increment → NULL + flagged",
        "sb_placeholder_flagged":  "Systembolaget ID: 'Nätvin' → NULL + flagged",
        "grape_names_normalised":  "Grape name instances normalised (synonyms)",
    }
    for key, label in labels.items():
        print(f"  {counters[key]:5d}  {label}")


if __name__ == "__main__":
    main()
