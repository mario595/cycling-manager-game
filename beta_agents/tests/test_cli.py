import json

from datetime import datetime, timezone

from beta_agents import __main__ as cli
from beta_agents.diary import Diary
from beta_agents.game_api import Response


def test_due_reads_the_diaries(capsys, tmp_path):
    for slug, stamp in [("youth", "2026-11-18 10:17"), ("trader", "2026-11-18 03:00"), ("money", "2026-11-18 14:00"), ("racer", "2026-11-13 13:28"), ("casual", "2026-11-18 03:00")]:
        Diary(tmp_path, slug, slug).append("visited", at=datetime.fromisoformat(stamp).replace(tzinfo=timezone.utc))
    assert cli.main(["due", "--diary-dir", str(tmp_path), "--now", "2026-11-18T15:17"], env={}) == 0
    assert capsys.readouterr().out.split() == ["racer", "trader"]


def test_everyone_is_due_with_no_diaries(capsys, tmp_path):
    assert cli.main(["due", "--diary-dir", str(tmp_path)], env={}) == 0
    assert len(capsys.readouterr().out.split()) == 5


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


class FakeGitHub:
    def __init__(self, diaries=None, branch=200, dispatch=204):
        self.diaries = diaries or {}
        self.branch = branch
        self.dispatch_status = dispatch
        self.requests = []

    def __call__(self, method, url, headers, data, timeout):
        self.requests.append((method, url, headers, data))
        assert headers["Authorization"] == "Bearer t"
        path = url.split("/repos/mario595/cycling-manager", 1)[1]
        if path == "/branches/beta-diaries":
            return Response(self.branch, {}, {})
        if path.startswith("/contents/diaries/"):
            slug = path.split("/")[-1].split(".md")[0]
            if slug not in self.diaries:
                return Response(404, {"message": "Not Found"}, {})
            return Response(200, f"# {slug}: diary\n\n## {self.diaries[slug]} UTC\n\nvisited\n", {})
        if path == "/actions/workflows/beta-agents.yml/dispatches":
            return Response(self.dispatch_status, None if self.dispatch_status == 204 else {"message": "nope"}, {})
        raise AssertionError(path)

    def dispatched(self):
        return [json.loads(d) for m, u, _, d in self.requests if m == "POST"]


def run_dispatch(github, now="2026-11-25T15:05", env=None):
    from beta_agents.dispatch import dispatch

    out = []
    code = dispatch(dict({"BETA_DISPATCH_TOKEN": "t"}, **(env or {})), datetime.fromisoformat(now).replace(tzinfo=timezone.utc), transport=github, echo=out.append)
    return code, out


FRESH = {"youth": "2026-11-25 12:00", "trader": "2026-11-25 12:01", "money": "2026-11-25 12:02", "racer": "2026-11-25 12:03", "casual": "2026-11-25 01:00"}


def test_dispatch_without_a_token_does_nothing(capsys):
    assert cli.main(["dispatch"], env={}) == 0
    assert "No BETA_DISPATCH_TOKEN" in capsys.readouterr().out


def test_dispatch_with_nobody_due_asks_github_for_nothing():
    github = FakeGitHub(FRESH)
    assert run_dispatch(github) == (0, ["Nobody is due."])
    assert github.dispatched() == []


def test_dispatch_starts_a_due_run_when_someone_is_due():
    github = FakeGitHub(dict(FRESH, racer="2026-11-25 07:00"))
    code, out = run_dispatch(github)
    assert code == 0 and out[0] == "Due: racer"
    assert github.dispatched() == [{"ref": "master", "inputs": {"tester": "due"}}]
    assert github.requests[-1][1] == "https://api.github.com/repos/mario595/cycling-manager/actions/workflows/beta-agents.yml/dispatches"


def test_a_tester_with_no_diary_is_due():
    github = FakeGitHub({k: v for k, v in FRESH.items() if k != "youth"})
    assert run_dispatch(github, env={"BETA_DISPATCH_REF": "main"})[1][0] == "Due: youth"
    assert github.dispatched() == [{"ref": "main", "inputs": {"tester": "due"}}]


def test_an_unreadable_diary_branch_dispatches_nothing():
    github = FakeGitHub(branch=404)
    code, out = run_dispatch(github)
    assert code == 1 and "contents" in out[-1]
    assert github.dispatched() == []


def test_a_refused_dispatch_fails():
    github = FakeGitHub({}, dispatch=403)
    code, out = run_dispatch(github)
    assert code == 1 and "answered 403" in out[-1]
