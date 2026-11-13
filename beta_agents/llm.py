"""The model, reached through an OpenAI-compatible chat completions endpoint.

Gemini's compatibility endpoint (the default), Mistral, Groq and OpenRouter all
speak this shape, so changing provider is three settings: the base URL, the
model and the key (beta_agents/README.md, *Choosing the model*).
"""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any, Callable

DEFAULT_BASE_URL = "https://generativelanguage.googleapis.com/v1beta/openai"
DEFAULT_MODEL = "gemini-3.5-flash-lite"


class LLMError(RuntimeError):
    """The model could not be used: a refused key, a spent quota, an outage."""


@dataclass
class HTTPResult:
    status: int
    body: str
    headers: dict[str, str]


def urllib_post(url: str, headers: dict[str, str], data: bytes, timeout: float) -> HTTPResult:
    request = urllib.request.Request(url, data=data, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(request, timeout=timeout) as raw:
            return HTTPResult(raw.status, raw.read().decode("utf-8", "replace"), {k.lower(): v for k, v in raw.headers.items()})
    except urllib.error.HTTPError as error:
        return HTTPResult(error.code, error.read().decode("utf-8", "replace"), {k.lower(): v for k, v in error.headers.items()})


Post = Callable[[str, dict[str, str], bytes, float], HTTPResult]


class ChatClient:
    def __init__(
        self,
        api_key: str,
        model: str = DEFAULT_MODEL,
        base_url: str = DEFAULT_BASE_URL,
        post: Post = urllib_post,
        sleep: Callable[[float], None] = time.sleep,
        clock: Callable[[], float] = time.monotonic,
        min_interval: float = 6.0,
        max_retries: int = 3,
        timeout: float = 120.0,
    ):
        if not api_key:
            raise LLMError("No model API key. Set BETA_LLM_API_KEY.")
        self.api_key = api_key
        self.model = model
        self.url = base_url.rstrip("/") + "/chat/completions"
        self.post = post
        self.sleep = sleep
        self.clock = clock
        self.min_interval = min_interval
        self.max_retries = max_retries
        self.timeout = timeout
        self._last_call: float | None = None
        self.calls = 0
        self.prompt_tokens = 0
        self.completion_tokens = 0

    def chat(self, messages: list[dict], tools: list[dict]) -> dict:
        """One model turn. Returns the assistant message as a dict with
        `content` and possibly `tool_calls`."""
        payload = {"model": self.model, "messages": messages, "tools": tools, "tool_choice": "auto", "temperature": 0.4}
        data = json.dumps(payload).encode()
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
        last_error = ""
        for attempt in range(self.max_retries + 1):
            self._pace()
            try:
                result = self.post(self.url, headers, data, self.timeout)
            except (urllib.error.URLError, TimeoutError, ConnectionError) as error:
                last_error = f"unreachable ({error})"
                self.sleep(5.0 * (attempt + 1))
                continue
            self.calls += 1
            if result.status == 200:
                return self._parse(result.body)
            last_error = f"{result.status}: {result.body[:300]}"
            if result.status == 429 or result.status >= 500:
                self.sleep(_retry_after(result.headers, default=5.0 * (attempt + 1)))
                continue
            break  # a 4xx other than 429 will not get better by retrying
        raise LLMError(f"The model call failed: {last_error}")

    def _pace(self) -> None:
        now = self.clock()
        if self._last_call is not None:
            wait = self.min_interval - (now - self._last_call)
            if wait > 0:
                self.sleep(wait)
        self._last_call = self.clock()

    def _parse(self, body: str) -> dict[str, Any]:
        try:
            response = json.loads(body)
            message = response["choices"][0]["message"]
        except (json.JSONDecodeError, KeyError, IndexError, TypeError) as error:
            raise LLMError(f"Unreadable model response: {body[:300]}") from error
        usage = response.get("usage") or {}
        self.prompt_tokens += usage.get("prompt_tokens", 0) or 0
        self.completion_tokens += usage.get("completion_tokens", 0) or 0
        return message


def _retry_after(headers: dict[str, str], default: float) -> float:
    try:
        return min(max(float(headers.get("retry-after", default)), 1.0), 60.0)
    except ValueError:
        return default
