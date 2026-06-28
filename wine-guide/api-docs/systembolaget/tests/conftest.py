"""
Shared fixtures for Systembolaget API probes.

Every fixture here makes live HTTP requests. If the suite starts returning
401s the API key has rotated — refresh from systembolaget.se DevTools
(Network tab → any api-extern.* request → Ocp-Apim-Subscription-Key).
"""

import pytest
import requests

API_BASE = "https://api-extern.systembolaget.se"
API_KEY = "8d39a7340ee7439f8b4c1e995c8f3e4a"

DEFAULT_HEADERS = {
    "Ocp-Apim-Subscription-Key": API_KEY,
    "Origin": "https://www.systembolaget.se",
    "Accept": "application/json",
    "User-Agent": "wine-guide-api-probe/1.0",
}


@pytest.fixture(scope="session")
def api_base():
    return API_BASE


@pytest.fixture(scope="session")
def api_key():
    return API_KEY


@pytest.fixture(scope="session")
def session():
    s = requests.Session()
    s.headers.update(DEFAULT_HEADERS)
    return s


@pytest.fixture(scope="session")
def catalog(session, api_base):
    """Full /v1/product response, fetched once per session (~7 MB)."""
    resp = session.get(f"{api_base}/sb-api-ecommerce/v1/product", timeout=60)
    resp.raise_for_status()
    return resp.json()


@pytest.fixture(scope="session")
def search_wine_page1(session, api_base):
    """First page of a wine-category search, shared across probes for structural inspection."""
    resp = session.get(
        f"{api_base}/sb-api-ecommerce/v1/productsearch/search",
        params={"categoryLevel1": "Vin", "page": 1},
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json()


@pytest.fixture(scope="session")
def sample_wine_product(search_wine_page1):
    """A live wine product lifted from page 1 of the search index."""
    products = search_wine_page1.get("products", [])
    assert products, "search returned no wine products"
    return products[0]


@pytest.fixture(scope="session")
def all_store_stock(session, api_base, sample_wine_product):
    """`/v1/site/stores/{productId}/` response for a sample wine (~650 KB)."""
    pid = sample_wine_product["productId"]
    resp = session.get(
        f"{api_base}/sb-api-ecommerce/v1/site/stores/{pid}/",
        timeout=60,
    )
    resp.raise_for_status()
    return resp.json()


@pytest.fixture(scope="session")
def sample_store_with_stock(all_store_stock):
    """A store entry from the all-store response that has positive stock for the sample wine."""
    for entry in all_store_stock["storeStocks"]:
        if entry["stockBalance"]["stock"] > 0:
            return entry
    raise RuntimeError("no store with positive stock found for the sample wine")


@pytest.fixture(scope="session")
def sitesearch_response(session, api_base):
    """`/v1/sitesearch/site` with a broad `q` — used for structural probes."""
    resp = session.get(
        f"{api_base}/sb-api-ecommerce/v1/sitesearch/site",
        params={"q": "stockholm", "includePredictions": "false"},
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json()


def _paginate_country(session, api_base, country, max_pages):
    """Iterate the search endpoint for a single country partition and return
    the collected product records."""
    products = []
    for page in range(1, max_pages + 1):
        resp = session.get(
            f"{api_base}/sb-api-ecommerce/v1/productsearch/search",
            params={"categoryLevel1": "Vin", "country": country, "page": page},
            timeout=30,
        )
        resp.raise_for_status()
        page_products = resp.json().get("products", [])
        if not page_products:
            break
        products.extend(page_products)
    return products


@pytest.fixture(scope="session")
def sverige_wines(session, api_base):
    """All wines under country=Sverige (small partition, ~350 wines, ~12 pages).

    Used to probe complete-coverage properties of single-country pagination.
    """
    return _paginate_country(session, api_base, "Sverige", max_pages=30)


@pytest.fixture(scope="session")
def italy_wine_sample(session, api_base):
    """A ~10-page sample of Italian wines from the search endpoint.

    Italy has a rich set of packaging/size variants (bag-in-box, half-bottles,
    magnums, etc.), so 10 pages (~300 wines) is enough to observe sibling-group
    structure without the expense of paginating the whole 130-page partition.
    """
    return _paginate_country(session, api_base, "Italien", max_pages=10)
