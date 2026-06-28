"""
Match Munskänkarna tasting rows to Systembolaget productNumbers.

Implements the verdict from product_code_analysis/findings.md:

  1. If the tasting code is itself a valid productNumber in the catalog,
     accept only if name+producer agree; otherwise flag exact_name_mismatch
     (recycled SKU).
  2. Else try sibling suffixes 01, 02, 06, 08, 09, 11 under the two-signal
     rule (name similar AND producer similar).
  3. Else no_match.

Thresholds: name_ok = sim >= 0.6 OR jaccard >= 0.5; producer_ok = sim >= 0.6.
"""

import re
import unicodedata
from difflib import SequenceMatcher

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


def compare(row, search_hit, catalog_hit):
    sb_name = ""
    sb_producer = ""
    sb_vintage = None
    in_search = search_hit is not None
    if search_hit is not None:
        bold = search_hit.get("productNameBold") or ""
        thin = search_hit.get("productNameThin") or ""
        sb_name = (bold + " " + thin).strip()
        sb_producer = search_hit.get("producerName") or ""
        sb_vintage = search_hit.get("vintage")
    elif catalog_hit is not None:
        sb_name = catalog_hit.get("productNameBold") or ""

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

      exact                  code is a valid productNumber; name+producer agree
      exact_name_mismatch    code is a valid productNumber but name/producer
                             disagree (recycled SKU)
      sibling_<ss>           code+<ss> valid AND name+producer agree
      sibling_<ss>_name_only sibling candidate exists, name agrees but
                             producer doesn't (low-confidence)
      no_match               nothing in catalog + no sibling agrees
    """
    code = row["code"]

    if code in catalog_by_pn or code in search_by_pn:
        cmp = compare(row, search_by_pn.get(code), catalog_by_pn.get(code))
        if cmp["name_ok"] and (cmp["producer_ok"] or not cmp["sb_producer"]):
            return code, "exact", cmp
        return code, "exact_name_mismatch", cmp

    fallback = None
    for suf in SIBLING_SUFFIXES:
        candidate = code + suf
        if candidate not in catalog_by_pn:
            continue
        cmp = compare(row, search_by_pn.get(candidate), catalog_by_pn.get(candidate))
        if cmp["name_ok"] and cmp["producer_ok"]:
            return candidate, f"sibling_{suf}", cmp
        if fallback is None and cmp["name_ok"]:
            fallback = (candidate, f"sibling_{suf}_name_only", cmp)

    if fallback is not None:
        return fallback
    return None, "no_match", None


STRONG_MATCH_PREFIXES = ("exact", "sibling_")


def is_strong_match(reason: str) -> bool:
    """A match we trust as identity — not recycled and not name-only."""
    if not reason:
        return False
    if reason == "exact_name_mismatch":
        return False
    if reason.endswith("_name_only"):
        return False
    return reason.startswith(STRONG_MATCH_PREFIXES)
