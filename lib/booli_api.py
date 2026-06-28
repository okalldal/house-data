"""
Thin client for the Booli Open API (https://api.booli.se).

Every behaviour relied on here is documented and (where possible) verified in
`api-docs/booli/`. The auth scheme is the four-param HMAC contract: each request
carries `callerId`, `time`, `unique`, and `hash = sha1(callerId+time+unique+key)`
(see api.md — the auth *failure* modes are verified by probes B001–B008; the
exact hash construction is PENDING B010, confirmable only with credentials).

Credentials come from the environment:

    export BOOLI_CALLER_ID=your-caller-id
    export BOOLI_KEY=your-private-key

Request an identity from api@booli.se (the live API says so — claim B004).
"""

from __future__ import annotations

import hashlib
import os
import secrets
import time
from typing import Iterator

import requests

API_BASE = "https://api.booli.se"


class BooliError(RuntimeError):
    """A non-2xx response from api.booli.se. Carries the plain-text error code."""

    def __init__(self, status: int, body: str):
        self.status = status
        self.body = body
        self.code = body.split(" - ", 1)[0] if " - " in body else body
        super().__init__(f"HTTP {status}: {body}")


class BooliClient:
    """Authenticated client for the Booli Open API.

    >>> client = BooliClient.from_env()
    >>> first_page = client.get("sold", areaId=76208, limit=50)
    >>> for sale in client.iter_sold(areaId=76208):
    ...     ...
    """

    def __init__(self, caller_id: str, key: str, *, base: str = API_BASE,
                 session: requests.Session | None = None):
        if not caller_id or not key:
            raise ValueError("caller_id and key are required (see api@booli.se)")
        self.caller_id = caller_id
        self.key = key
        self.base = base.rstrip("/")
        self.session = session or requests.Session()
        self.session.headers.setdefault("Accept", "application/json")
        self.session.headers.setdefault("User-Agent", "house-data/1.0")

    @classmethod
    def from_env(cls, **kwargs) -> "BooliClient":
        return cls(
            os.environ.get("BOOLI_CALLER_ID", ""),
            os.environ.get("BOOLI_KEY", ""),
            **kwargs,
        )

    # -- auth -----------------------------------------------------------------

    def _auth_params(self) -> dict:
        """Build the four Booli auth params for the current instant.

        hash = sha1(callerId + time + unique + key), hex digest.
        """
        unique = secrets.token_hex(8)
        ts = str(int(time.time()))
        digest = hashlib.sha1(
            (self.caller_id + ts + unique + self.key).encode("utf-8")
        ).hexdigest()
        return {"callerId": self.caller_id, "time": ts, "unique": unique,
                "hash": digest}

    # -- requests -------------------------------------------------------------

    def get(self, endpoint: str, **params) -> dict:
        """GET a Booli endpoint with auth, returning the parsed JSON body.

        Raises BooliError on a non-2xx response (the body is plain text, not
        JSON — claim B005 — so we read .text for errors).
        """
        url = f"{self.base}/{endpoint.lstrip('/')}"
        resp = self.session.get(url, params={**params, **self._auth_params()},
                                timeout=30)
        if not resp.ok:
            raise BooliError(resp.status_code, resp.text.strip())
        return resp.json()

    # -- high-level helpers ---------------------------------------------------

    def iter_sold(self, *, page_size: int = 100, max_records: int | None = None,
                  **filters) -> Iterator[dict]:
        """Yield every sold-home record matching `filters`, paging via offset.

        `filters` are passed straight through to /sold (e.g. areaId=, q=,
        minSoldDate=, objectType=). Pagination relies on `totalCount` and
        `offset` (claims B016/B017, PENDING until credentialled).
        """
        offset = 0
        seen = 0
        while True:
            data = self.get("sold", limit=page_size, offset=offset, **filters)
            batch = data.get("sold", [])
            if not batch:
                break
            for item in batch:
                yield item
                seen += 1
                if max_records is not None and seen >= max_records:
                    return
            total = data.get("totalCount", 0)
            offset += len(batch)
            if offset >= total:
                break

    def resolve_area(self, name: str) -> list[dict]:
        """Resolve a place name to candidate areas via /areas (for areaId lookup)."""
        return self.get("areas", q=name).get("areas", [])
