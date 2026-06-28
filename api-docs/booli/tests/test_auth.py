"""
Probes for the Booli Open API auth contract and routing.

These probes need NO credentials — they observe how api.booli.se rejects
unauthenticated and malformed requests, and which paths are routed at all.

Each test's first docstring line is the claim it establishes.
"""

ENDPOINTS_REQUIRING_AUTH = ["listings", "sold", "areas", "residences"]


def _get(session, api_base, endpoint, **params):
    return session.get(f"{api_base}/{endpoint}", params=params, timeout=30)


def test_B001_listings_requires_auth(session, api_base):
    """A /listings request with no auth params is rejected with HTTP 403."""
    resp = _get(session, api_base, "listings")
    assert resp.status_code == 403


def test_B002_missing_param_error_names_the_four_params(session, api_base):
    """The missing-auth error body names exactly the four required params: callerId, unique, time, hash."""
    resp = _get(session, api_base, "listings")
    body = resp.text
    assert body.startswith("FAILURE_MISSING_PARAM")
    for param in ("callerId", "unique", "time", "hash"):
        assert param in body, f"{param} not mentioned in error body: {body!r}"


def test_B003_sold_requires_the_same_auth(session, api_base):
    """/sold (the past-sales endpoint) enforces the same auth contract as /listings."""
    resp = _get(session, api_base, "sold")
    assert resp.status_code == 403
    assert resp.text.startswith("FAILURE_MISSING_PARAM")


def test_B004_unknown_identity_rejected(session, api_base):
    """All four auth params present but with an unknown callerId yields 403 FAILURE_IDENTITY_NOT_FOUND, pointing the caller at api@booli.se."""
    resp = _get(
        session,
        api_base,
        "listings",
        callerId="house-data-probe-no-such-identity",
        unique="abc123",
        time="1700000000",
        hash="0" * 40,
    )
    assert resp.status_code == 403
    assert resp.text.startswith("FAILURE_IDENTITY_NOT_FOUND")
    assert "api@booli.se" in resp.text


def test_B005_error_body_is_plaintext_not_json(session, api_base):
    """Error responses are plain-text 'CODE - message' strings, not JSON objects, even though GET errors carry an application/json content-type."""
    import json

    resp = _get(session, api_base, "listings")
    # content-type header claims JSON on GET...
    assert "application/json" in resp.headers.get("content-type", "")
    # ...but the body does not parse as JSON.
    try:
        json.loads(resp.text)
        parsed = True
    except ValueError:
        parsed = False
    assert parsed is False
    # The shape is "ERRORCODE - human-readable message".
    assert " - " in resp.text
    code = resp.text.split(" - ", 1)[0]
    assert code.isupper() and code.startswith("FAILURE_")


def test_B006_documented_data_endpoints_are_routed(session, api_base):
    """/listings, /sold, /areas and /residences are all routed endpoints (they answer with the auth error, not a 404)."""
    for endpoint in ENDPOINTS_REQUIRING_AUTH:
        resp = _get(session, api_base, endpoint)
        assert resp.status_code == 403, f"{endpoint} returned {resp.status_code}"
        assert resp.text.startswith("FAILURE_MISSING_PARAM"), endpoint


def test_B007_unknown_endpoint_is_404(session, api_base):
    """An unknown path returns HTTP 404, distinguishing a non-existent endpoint from an unauthenticated-but-valid one (403)."""
    resp = _get(session, api_base, "this-endpoint-does-not-exist")
    assert resp.status_code == 404


def test_B008_post_also_requires_auth(session, api_base):
    """POST is subject to the same auth contract — an unauthenticated POST to /listings is rejected with the missing-param error, so the auth gate is not method-specific."""
    resp = session.post(f"{api_base}/listings", timeout=30)
    assert resp.status_code == 403
    assert resp.text.startswith("FAILURE_MISSING_PARAM")
