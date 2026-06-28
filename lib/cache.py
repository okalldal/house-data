"""
Small caching + atomic-write helpers, mirroring wine-guide's lib/cache.py.

Booli's Open API is rate-limited and credentialled, so we cache aggressively:
fetched pages land under `cache/` and never need re-fetching for a given query.
"""

from __future__ import annotations

import json
import os
import tempfile
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
CACHE_DIR = REPO_ROOT / "cache"
DATA_DIR = REPO_ROOT / "data"


def _atomic_write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(text)
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


def write_json(path: Path | str, obj) -> None:
    """Atomically write `obj` as pretty JSON."""
    _atomic_write(Path(path), json.dumps(obj, ensure_ascii=False, indent=2))


def read_json(path: Path | str):
    """Read a JSON file, or return None if it does not exist."""
    p = Path(path)
    if not p.exists():
        return None
    return json.loads(p.read_text(encoding="utf-8"))


def is_fresh(path: Path | str, ttl_seconds: float) -> bool:
    """True if `path` exists and was modified within `ttl_seconds`."""
    p = Path(path)
    return p.exists() and (time.time() - p.stat().st_mtime) < ttl_seconds


def cache_path(*parts: str) -> Path:
    """Build a path under cache/ (parents not created until written)."""
    return CACHE_DIR.joinpath(*parts)


def data_path(*parts: str) -> Path:
    """Build a path under data/."""
    return DATA_DIR.joinpath(*parts)
