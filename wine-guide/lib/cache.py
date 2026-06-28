"""
Disk cache helpers shared across the pipeline scripts.

- JSON with atomic replace (tmp file then rename).
- Gzipped JSON for the per-productId stock files (many small files).
- TTL helper for deciding when a cache entry is stale.
"""

import gzip
import json
import os
from datetime import datetime, timezone
from pathlib import Path


def now_utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def write_json(path: Path, obj) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(obj, ensure_ascii=False))
    os.replace(tmp, path)


def read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def write_json_gz(path: Path, obj) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with gzip.open(tmp, "wt", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False)
    os.replace(tmp, path)


def read_json_gz(path: Path):
    with gzip.open(path, "rt", encoding="utf-8") as f:
        return json.load(f)


def is_fresh(path: Path, max_age_hours: float) -> bool:
    """True iff `path` exists and was modified within the last max_age_hours."""
    if not path.exists():
        return False
    mtime = datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc)
    age_s = (datetime.now(timezone.utc) - mtime).total_seconds()
    return age_s <= max_age_hours * 3600.0


# --- Conventional paths -------------------------------------------------------

REPO_ROOT = Path(__file__).resolve().parent.parent
CACHE_DIR = REPO_ROOT / "cache"
DATA_DIR = REPO_ROOT / "data"

CATALOG_PATH = CACHE_DIR / "catalog.json"
WINE_SEARCH_PATH = CACHE_DIR / "wine_search.json"
STORES_PATH = CACHE_DIR / "stores.json"
DEPOT_IDS_PATH = CACHE_DIR / "depot_ids.json"
STOCK_DIR = CACHE_DIR / "stock"

WINES_MATCHED_CSV = DATA_DIR / "wines_matched.csv"


def stock_path(product_id: str) -> Path:
    return STOCK_DIR / f"{product_id}.json.gz"
