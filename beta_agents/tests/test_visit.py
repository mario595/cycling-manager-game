import json
from datetime import datetime, timezone

import pytest

from beta_agents import testers
from beta_agents.diary import Diary
from beta_agents.game_api import GameAPI
from beta_agents.llm import LLMError
from beta_agents.prompt import opening_message, staging_briefing, system_prompt
from beta_agents.tools import Toolbox, operations_from_schema
from beta_agents.visit import run_visit

from .conftest import FakeTransport

NOW = datetime(2026, 11, 13, 12, 17, tzinfo=timezone.utc)


def call(name, args, id_="c1"):
    return {"id": id_, "type": "function", "function": {"name": name, "arguments": json.dumps(args)}}


class ScriptedLLM:
    def __init__(self, turns):
        self.turns = list(turns)
        self.seen = []

    def chat(self, messages, tools):
        self.seen.append((list(messages), tools))
        turn = self.turns.pop(0)
        if isinstance(turn, Exception):
            raise turn
        return turn


@pytest.fixture
def setup(schema, tmp_path):
    transport = FakeTransport(
        {
            ("GET", "/api/accounts/me/"): (200, {"team": None}),
            ("POST", "/api/feedback/reports/"): (201, {"id": 1}),
            ("POST", "/api/staff/trainer/fire/"): (500, "Server Error"),
        }
    )
    box = Toolbox(GameAPI("http://g", "k", transport=transport), operations_from_schema(schema))
    tester = testers.get("racer")
    return tester, box, Diary(tmp_path, tester.slug, tester.display_name), transport


def test_a_full_visit(setup):
    tester, box, diary, transport = setup
    diary.append("last time: expected to win auction 3", at=datetime(2026, 11, 13, 8, tzinfo=timezone.utc))
    llm = ScriptedLLM(
        [
            {"content": "Let me look.", "tool_calls": [call("get_me", {})]},
            {"tool_calls": [call("fire_trainer", {}, "a"), call("report_a_problem", {"category": "bug", "text": "500"}, "b")]},
            {"tool_calls": [call("finish_visit", {"diary_entry": "Fired nobody; reported a 500."})]},
        ]
    )
    outcome = run_visit(tester, box, llm, diary, now=NOW, echo=lambda *_: None)
    assert outcome.finished and not outcome.cut_short
    assert (outcome.steps, outcome.tool_calls, outcome.reports_filed, outcome.api_errors) == (3, 4, 1, 1)
    first_messages, tools = llm.seen[0]
    assert first_messages[0]["role"] == "system" and "beta tester" in first_messages[0]["content"]
    assert "expected to win auction 3" in first_messages[1]["content"]
    assert {t["function"]["name"] for t in tools} >= {"finish_visit", "get_me", "report_a_problem"}
    # every tool call got its result, in order, with its id
    last = llm.seen[-1][0]
    assert [m.get("tool_call_id") for m in last if m["role"] == "tool"] == ["c1", "a", "b"]
    entries = diary.last_entries()
    assert entries[-1].startswith("## 2026-11-13 12:17 UTC") and "reported a 500" in entries[-1]
    assert "1 reports filed" in entries[-1]


def test_report_cap_holds(setup):
    tester, box, diary, transport = setup
    report = lambda i: call("report_a_problem", {"category": "bug", "text": f"r{i}"}, f"r{i}")
    llm = ScriptedLLM(
        [
            {"tool_calls": [report(1), report(2), report(3), report(4)]},
            {"tool_calls": [call("finish_visit", {"diary_entry": "done"})]},
        ]
    )
    outcome = run_visit(tester, box, llm, diary, now=NOW, echo=lambda *_: None)
    assert (outcome.reports_filed, outcome.reports_refused) == (3, 1)
    assert sum(1 for r in transport.requests if r[1].endswith("/api/feedback/reports/")) == 3


def test_step_cap_writes_a_harness_entry(setup):
    tester, box, diary, _ = setup
    llm = ScriptedLLM([{"tool_calls": [call("get_me", {})]}] * 3)
    outcome = run_visit(tester, box, llm, diary, max_steps=3, now=NOW, echo=lambda *_: None)
    assert outcome.cut_short and outcome.steps == 3
    assert "ran out of steps" in diary.last_entries()[-1]


def test_a_model_that_stops_is_nudged_once(setup):
    tester, box, diary, _ = setup
    llm = ScriptedLLM([{"content": "All good."}, {"tool_calls": [call("finish_visit", {"diary_entry": "ok"})]}])
    outcome = run_visit(tester, box, llm, diary, now=NOW, echo=lambda *_: None)
    assert outcome.finished
    assert "finish_visit" in llm.seen[1][0][-1]["content"]

    llm = ScriptedLLM([{"content": "a"}, {"content": "b"}])
    outcome = run_visit(tester, box, llm, diary, now=NOW, echo=lambda *_: None)
    assert outcome.cut_short and "stopped without writing one" in diary.last_entries()[-1]


def test_model_failure_before_anything_skips_the_visit(setup):
    tester, box, diary, _ = setup
    with pytest.raises(LLMError):
        run_visit(tester, box, ScriptedLLM([LLMError("401")]), diary, now=NOW, echo=lambda *_: None)
    assert diary.last_entries() == []


def test_model_failure_mid_visit_is_recorded(setup):
    tester, box, diary, _ = setup
    llm = ScriptedLLM([{"tool_calls": [call("get_me", {})]}, LLMError("quota spent")])
    outcome = run_visit(tester, box, llm, diary, now=NOW, echo=lambda *_: None)
    assert outcome.error == "quota spent"
    assert "the model failed (quota spent)" in diary.last_entries()[-1]


def test_bad_arguments_are_tolerated(setup):
    tester, box, diary, _ = setup
    broken = {"id": "x", "function": {"name": "get_me", "arguments": "{not json"}}
    llm = ScriptedLLM([{"tool_calls": [broken]}, {"tool_calls": [call("finish_visit", {"diary_entry": "ok"})]}])
    assert run_visit(tester, box, llm, diary, now=NOW, echo=lambda *_: None).finished


def test_prompt_pieces():
    prompt = " ".join(system_prompt(testers.get("youth")).split())
    assert "development squad" in prompt  # the persona
    assert "report_a_problem" in prompt and "at most 3 reports" in prompt
    assert "How the game works" in prompt  # the player's guide
    assert "24 times faster" in prompt  # the staging briefing
    assert "Keep it in step with the code" not in staging_briefing()  # its maintainers' note is left out
    assert "first visit" in opening_message([], "now")
