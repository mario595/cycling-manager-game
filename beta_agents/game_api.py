"""The game's API, as a player's client sees it.

Plain `urllib.request`: no cookie jar, so a token request never carries a
session cookie (which would make the server treat it as a browser and ask for
CSRF on writes; api/README.md, *Tokens*). Every request sends the tester's
`Authorization: Bearer <key>`.
"""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Any, Callable

USER_AGENT = "velodra-beta-tester/1"


@dataclass
class Response:
    status: int
    body: Any  # parsed JSON, or the raw text when it isn't JSON
    headers: dict[str, str]


def urllib_transport(method: str, url: str, headers: dict[str, str], data: bytes | None, timeout: float) -> Response:
    """Send one request. HTTP errors are returned as responses, not raised:
    a 4xx is something the tester is meant to see."""
    request = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(request, timeout=timeout) as raw:
            status, payload, response_headers = raw.status, raw.read(), dict(raw.headers.items())
    except urllib.error.HTTPError as error:
        status, payload, response_headers = error.code, error.read(), dict(error.headers.items())
    text = payload.decode("utf-8", errors="replace")
    try:
        body: Any = json.loads(text) if text else None
    except json.JSONDecodeError:
        body = text
    return Response(status=status, body=body, headers={k.lower(): v for k, v in response_headers.items()})


Transport = Callable[[str, str, dict[str, str], "bytes | None", float], Response]


class GameAPIError(RuntimeError):
    """The server could not be used at all (down, refusing the key)."""


class GameAPI:
    def __init__(
        self,
        base_url: str,
        key: str | None,
        transport: Transport = urllib_transport,
        sleep: Callable[[float], None] = time.sleep,
        timeout: float = 30.0,
        max_429_retries: int = 3,
    ):
        self.base_url = base_url.rstrip("/")
        self.key = key
        self.transport = transport
        self.sleep = sleep
        self.timeout = timeout
        self.max_429_retries = max_429_retries
        self.calls = 0

    def call(self, method: str, path: str, body: Any = None, query: dict[str, Any] | None = None) -> Response:
        url = self.base_url + path
        if query:
            url += "?" + urllib.parse.urlencode({k: v for k, v in query.items() if v is not None})
        headers = {"Accept": "application/json", "User-Agent": USER_AGENT}
        if self.key:
            headers["Authorization"] = f"Bearer {self.key}"
        data = None
        if body is not None:
            data = json.dumps(body).encode()
            headers["Content-Type"] = "application/json"
        for attempt in range(self.max_429_retries + 1):
            self.calls += 1
            try:
                response = self.transport(method, url, headers, data, self.timeout)
            except (urllib.error.URLError, TimeoutError, ConnectionError) as error:
                raise GameAPIError(f"{method} {path}: server unreachable ({error})") from error
            if response.status != 429 or attempt == self.max_429_retries:
                return response
            self.sleep(_retry_after(response))
        raise AssertionError("unreachable")  # pragma: no cover

    def schema(self) -> dict:
        """The live OpenAPI schema, as JSON. Raises if the server or the key
        is unusable, which skips the visit before anything else happens."""
        response = self.call("GET", "/api/schema/", query={"format": "json"})
        if response.status != 200 or not isinstance(response.body, dict):
            raise GameAPIError(f"GET /api/schema/ answered {response.status}: {str(response.body)[:300]}")
        return response.body


def _retry_after(response: Response) -> float:
    try:
        return min(max(float(response.headers.get("retry-after", "5")), 1.0), 60.0)
    except ValueError:
        return 5.0

