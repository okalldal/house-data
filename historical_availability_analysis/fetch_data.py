"""
fetch_data.py  -  Ensure catalog + wine-search caches exist.

The catalog and search caches are owned by product_code_analysis (that
analysis also uses them). We piggy-back on them rather than duplicating
the ~46 MB of JSON.

If product_code_analysis/cache is empty, we invoke its fetcher.
"""

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).parent
SIBLING_CACHE = ROOT.parent / "product_code_analysis" / "cache"
CATALOG = SIBLING_CACHE / "catalog.json"
SEARCH = SIBLING_CACHE / "wine_search.json"


def main():
    if CATALOG.exists() and SEARCH.exists():
        print(f"[catalog+search] using cached {SIBLING_CACHE}", file=sys.stderr)
        return
    sibling_fetch = ROOT.parent / "product_code_analysis" / "fetch_data.py"
    print(f"[catalog+search] missing, running {sibling_fetch}", file=sys.stderr)
    subprocess.check_call([sys.executable, str(sibling_fetch)])


if __name__ == "__main__":
    main()
