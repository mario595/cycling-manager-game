import urllib.error

import pytest

from beta_agents.game_api import GameAPI, GameAPIError, Response, urllib_transport


def test_429_is_waited_out():
    answers = [Response(429, {}, {"retry-after": "3"}), Response(200, {"ok": 1}, {})]
    slept = []
    api = GameAPI("http://g", "k", transport=lambda *a: answers.pop(0), sleep=slept.append)
    assert api.call("GET", "/api/x/").body == {"ok": 1}
    assert slept == [3.0]
    assert api.calls == 2


def test_429_gives_up_after_retries():
    slept = []
    api = GameAPI("http://g", "k", transport=lambda *a: Response(429, {}, {"retry-after": "bad"}), sleep=slept.append, max_429_retries=2)
    assert api.call("GET", "/x/").status == 429
    assert slept == [5.0, 5.0]


def test_unreachable_server():
    def down(*a):
        raise urllib.error.URLError("refused")

    with pytest.raises(GameAPIError):
        GameAPI("http://g", "k", transport=down).call("GET", "/x/")


def test_schema_must_be_json():
    api = GameAPI("http://g", "k", transport=lambda *a: Response(403, {"detail": "no"}, {}))
    with pytest.raises(GameAPIError, match="403"):
        api.schema()
    ok = GameAPI("http://g", "k", transport=lambda *a: Response(200, {"paths": {}}, {}))
    assert ok.schema() == {"paths": {}}


def test_urllib_transport_reads_errors_as_responses(monkeypatch):
    import io

    def fake_urlopen(request, timeout):
        raise urllib.error.HTTPError(request.full_url, 400, "Bad", {"X-A": "1"}, io.BytesIO(b'{"detail": "bad"}'))

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    response = urllib_transport("GET", "http://g/x/", {}, None, 1)
    assert (response.status, response.body, response.headers) == (400, {"detail": "bad"}, {"x-a": "1"})


def test_urllib_transport_success_and_text(monkeypatch):
    class Raw:
        status = 200
        headers = {"Content-Type": "text/plain"}

        def read(self):
            return b"hello"

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    monkeypatch.setattr("urllib.request.urlopen", lambda request, timeout: Raw())
    assert urllib_transport("GET", "http://g/x/", {}, None, 1).body == "hello"
