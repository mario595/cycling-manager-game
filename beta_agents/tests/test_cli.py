import json

from beta_agents import __main__ as cli
from beta_agents.game_api import Response


def test_due(capsys):
    assert cli.main(["due", "--hour", "2"], env={}) == 0
    assert capsys.readouterr().out.split() == ["trader"]
    assert cli.main(["due", "--hour", "3"], env={}) == 0
    assert capsys.readouterr().out.split() == ["casual"]


def test_unknown_tester(capsys):
    assert cli.main(["visit", "nobody"], env={}) == 2


def test_visit_without_a_key_is_skipped(capsys):
    assert cli.main(["visit", "youth"], env={}) == 1
    assert "BETA_KEY_YOUTH" in capsys.readouterr().err


def test_visit_with_an_unreachable_server(monkeypatch, capsys):
    def down(*a):
        raise ConnectionError("nope")

    monkeypatch.setattr("beta_agents.game_api.urllib_transport", down)
    monkeypatch.setattr(cli.GameAPI.__init__, "__defaults__", (down,) + cli.GameAPI.__init__.__defaults__[1:])
    code = cli.main(["--base-url", "http://127.0.0.1:9", "visit", "youth"], env={"BETA_KEY_YOUTH": "k", "BETA_LLM_API_KEY": "x"})
    assert code == 1
    assert "Visit skipped" in capsys.readouterr().err


def test_register_and_tools(monkeypatch, capsys, schema):
    sent = []

    def transport(method, url, headers, data, timeout):
        sent.append((method, url, headers, data))
        if url.endswith("/register/"):
            return Response(201, {"display_name": "x"}, {})
        return Response(200, schema, {})

    monkeypatch.setattr(cli.GameAPI.__init__, "__defaults__", (transport,) + cli.GameAPI.__init__.__defaults__[1:])
    assert cli.main(["--base-url", "http://g", "register", "trader"], env={}) == 0
    out = capsys.readouterr().out
    assert "issue_api_token beta-trader@velodra.test" in out and "BETA_KEY_TRADER" in out
    body = json.loads(sent[0][3])
    assert body["email"] == "beta-trader@velodra.test" and len(body["password"]) > 20
    assert "Authorization" not in sent[0][2]

    assert cli.main(["--base-url", "http://g", "tools"], env={"BETA_KEY_MONEY": "k"}) == 0
    out = capsys.readouterr().out
    assert "set_squad" in out and "finish_visit" in out and "login" not in out
    assert sent[-1][2]["Authorization"] == "Bearer k"


def test_register_failure(monkeypatch, capsys):
    transport = lambda *a: Response(400, {"email": ["taken"]}, {})
    monkeypatch.setattr(cli.GameAPI.__init__, "__defaults__", (transport,) + cli.GameAPI.__init__.__defaults__[1:])
    assert cli.main(["--base-url", "http://g", "register", "trader"], env={}) == 1
