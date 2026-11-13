import json
import urllib.error

import pytest

from beta_agents.llm import ChatClient, HTTPResult, LLMError


def ok(message, usage=None):
    return HTTPResult(200, json.dumps({"choices": [{"message": message}], "usage": usage or {"prompt_tokens": 10, "completion_tokens": 2}}), {})


def client(answers, **kw):
    posted, slept = [], []

    def post(url, headers, data, timeout):
        posted.append((url, headers, json.loads(data)))
        answer = answers.pop(0)
        if isinstance(answer, Exception):
            raise answer
        return answer

    times = iter(range(0, 1000))
    c = ChatClient("key", model="m", base_url="https://llm/v1/", post=post, sleep=slept.append, clock=lambda: next(times), **kw)
    return c, posted, slept


def test_a_turn():
    c, posted, _ = client([ok({"role": "assistant", "content": "hi"})])
    assert c.chat([{"role": "user", "content": "x"}], [{"type": "function"}]) == {"role": "assistant", "content": "hi"}
    url, headers, payload = posted[0]
    assert url == "https://llm/v1/chat/completions"
    assert headers["Authorization"] == "Bearer key"
    assert payload["model"] == "m" and payload["tool_choice"] == "auto"
    assert (c.calls, c.prompt_tokens, c.completion_tokens) == (1, 10, 2)


def test_pacing_spaces_calls():
    c, _, slept = client([ok({}), ok({})], min_interval=5)
    c.chat([], [])
    c.chat([], [])
    assert slept and slept[0] > 0


def test_retries_429_and_5xx_then_succeeds():
    c, _, slept = client([HTTPResult(429, "slow", {"retry-after": "2"}), HTTPResult(503, "down", {}), ok({"content": "x"})], min_interval=0)
    assert c.chat([], [])["content"] == "x"
    assert 2.0 in slept


def test_unreachable_then_succeeds():
    c, _, _ = client([urllib.error.URLError("x"), ok({"content": "y"})], min_interval=0)
    assert c.chat([], [])["content"] == "y"


def test_refused_key_fails_at_once():
    c, posted, _ = client([HTTPResult(401, "Upgrade to activate your API keys", {})], min_interval=0)
    with pytest.raises(LLMError, match="401"):
        c.chat([], [])
    assert len(posted) == 1


def test_gives_up_after_retries():
    c, _, _ = client([HTTPResult(429, "", {})] * 3, min_interval=0, max_retries=2)
    with pytest.raises(LLMError, match="429"):
        c.chat([], [])


def test_unreadable_response():
    c, _, _ = client([HTTPResult(200, "{}", {})], min_interval=0)
    with pytest.raises(LLMError, match="Unreadable"):
        c.chat([], [])


def test_needs_a_key():
    with pytest.raises(LLMError):
        ChatClient("")
