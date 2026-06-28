"""
Probes for endpoints that require user-session authentication (JWT) in
addition to the frontend subscription key.

We do not hold a JWT, so every request here is made with the subscription
key alone. The probes characterise what the API returns in that
partial-auth state — which is what an application without a logged-in
user session will see.

Each test's first docstring line is the claim it establishes.
"""

import requests


def test_C110_taste_match_requires_jwt(session, api_base, sample_wine_product):
    """The taste-match endpoint `/v1/product/{productId}/recommended` requires a user JWT in addition to the subscription key; calling it with the subscription key alone returns HTTP 401 with a `JWT not present.` message."""
    pid = sample_wine_product["productId"]
    resp = session.get(
        f"{api_base}/sb-api-ecommerce/v1/product/{pid}/recommended",
        timeout=30,
    )
    assert resp.status_code == 401
    assert "JWT" in resp.json().get("message", "")


def test_C111_productfeedback_requires_jwt(session, api_base):
    """`/v1/productfeedback/` requires a user JWT; without one it returns HTTP 401 with `JWT not present.`."""
    resp = session.get(
        f"{api_base}/sb-api-ecommerce/v1/productfeedback/",
        timeout=30,
    )
    assert resp.status_code == 401
    assert "JWT" in resp.json().get("message", "")


def test_C112_productnotification_list_requires_jwt(session, api_base):
    """`/v1/productnotification/list/` requires a user JWT; without one it returns HTTP 401."""
    resp = session.get(
        f"{api_base}/sb-api-ecommerce/v1/productnotification/list/",
        timeout=30,
    )
    assert resp.status_code == 401


def test_C113_legacy_recommendations_path_does_not_exist(session, api_base, sample_wine_product):
    """The path `/v1/productrecommendations/getrecommendations/{productId}` returns HTTP 404 — despite being named in the legacy field notes, the endpoint either moved or never existed on api-extern. Do not rely on this URL."""
    pid = sample_wine_product["productId"]
    resp = session.get(
        f"{api_base}/sb-api-ecommerce/v1/productrecommendations/getrecommendations/{pid}",
        timeout=30,
    )
    assert resp.status_code == 404


def test_C114_beveragelist_returns_404_without_jwt(session, api_base):
    """`/v1/beveragelist/` returns HTTP 404 when called without a JWT — behaviour differs from other user-gated endpoints, which return 401. The 404 likely indicates the route requires a path component (e.g. a list id) that can only be obtained through the authenticated flow."""
    resp = session.get(
        f"{api_base}/sb-api-ecommerce/v1/beveragelist/",
        timeout=30,
    )
    assert resp.status_code == 404


def test_C115_401_with_key_carries_JWT_not_present_message(session, api_base, sample_wine_product):
    """The API distinguishes two kinds of 401: missing subscription key → generic rejection (no JSON body), vs missing JWT on an authenticated-only route → HTTP 401 with a JSON body `{statusCode: 401, message: "JWT not present."}`."""
    # Missing subscription key: generic 401
    missing_key = requests.get(
        f"{api_base}/sb-api-ecommerce/v1/product",
        headers={"Origin": "https://www.systembolaget.se", "Accept": "application/json"},
        timeout=30,
    )
    assert missing_key.status_code == 401

    # With key but no JWT, on an auth-only route: structured 401
    pid = sample_wine_product["productId"]
    missing_jwt = session.get(
        f"{api_base}/sb-api-ecommerce/v1/product/{pid}/recommended",
        timeout=30,
    )
    assert missing_jwt.status_code == 401
    body = missing_jwt.json()
    assert body.get("statusCode") == 401
    assert body.get("message") == "JWT not present."
