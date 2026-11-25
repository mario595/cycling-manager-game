import dataclasses
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
DONE = "ok.\nCritical observation: the market was empty."


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
    # These tests are about the tool loop, so the tester may finish early. The
    # minimum-effort rule has its own tests below, with the real racer.
    tester = dataclasses.replace(testers.get("racer"), min_tool_calls=0)
    return tester, box, Diary(tmp_path, tester.slug, tester.display_name), transport


def test_a_full_visit(setup):
    tester, box, diary, transport = setup
    diary.append("last time: expected to win auction 3", at=datetime(2026, 11, 13, 8, tzinfo=timezone.utc))
    llm = ScriptedLLM(
        [
            {"content": "Let me look.", "tool_calls": [call("get_me", {})]},
            {"tool_calls": [call("fire_trainer", {}, "a"), call("report_a_problem", {"category": "bug", "text": "500"}, "b")]},
            {"tool_calls": [call("finish_visit", {"diary_entry": "Fired nobody; reported a 500.\nCritical observation: firing gave a 500."})]},
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
            {"tool_calls": [call("finish_visit", {"diary_entry": DONE})]},
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
    llm = ScriptedLLM([{"content": "All good."}, {"tool_calls": [call("finish_visit", {"diary_entry": DONE})]}])
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
    llm = ScriptedLLM([{"tool_calls": [broken]}, {"tool_calls": [call("finish_visit", {"diary_entry": DONE})]}])
    assert run_visit(tester, box, llm, diary, now=NOW, echo=lambda *_: None).finished


def test_prompt_pieces():
    prompt = " ".join(system_prompt(testers.get("youth")).split())
    assert "development squad" in prompt  # the persona
    assert "report_a_problem" in prompt and "at most 3 reports" in prompt
    assert "How the game works" in prompt  # the player's guide
    assert "24 times faster" in prompt  # the staging briefing
    assert "Keep it in step with the code" not in staging_briefing()  # its maintainers' note is left out
    assert "first visit" in opening_message([], "now")


def test_provider_extras_on_a_tool_call_go_back_to_the_model(setup):
    # Gemini 3 refuses a history whose tool calls lost their thought signature.
    tester, box, diary, _ = setup
    signed = call("get_me", {})
    signed["extra_content"] = {"google": {"thought_signature": "sig-123"}}
    llm = ScriptedLLM([{"tool_calls": [signed]}, {"tool_calls": [call("finish_visit", {"diary_entry": DONE})]}])
    run_visit(tester, box, llm, diary, now=NOW, echo=lambda _: None)
    history, _ = llm.seen[1]
    echoed = next(m for m in history if m["role"] == "assistant")["tool_calls"][0]
    assert echoed["extra_content"] == {"google": {"thought_signature": "sig-123"}}
    assert echoed["function"]["name"] == "get_me"


def finish(text=DONE, id_="f"):
    return {"tool_calls": [call("finish_visit", {"diary_entry": text}, id_)]}


def looks(n):
    return {"tool_calls": [call("get_me", {}, f"g{i}") for i in range(n)]}


def test_an_early_finish_is_pushed_back_once_then_saves(setup):
    _, box, diary, _ = setup
    racer = testers.get("racer")
    llm = ScriptedLLM([looks(3), finish(id_="f1"), finish(id_="f2")])
    outcome = run_visit(racer, box, llm, diary, now=NOW, echo=lambda *_: None)
    assert outcome.finished and outcome.pushbacks == 1
    refusal = next(m for m in llm.seen[2][0] if m.get("tool_call_id") == "f1")
    assert '"saved": false' in refusal["content"] and "only 3 tool calls" in refusal["content"]
    assert "focus area, finances" in refusal["content"]  # the first visit's focus


def test_enough_looking_is_not_pushed_back(setup):
    _, box, diary, _ = setup
    llm = ScriptedLLM([looks(12), finish()])
    outcome = run_visit(testers.get("racer"), box, llm, diary, now=NOW, echo=lambda *_: None)
    assert outcome.finished and outcome.pushbacks == 0


def test_casual_may_keep_its_visits_short_and_has_no_focus(setup):
    _, box, diary, _ = setup
    casual = testers.get("casual")
    llm = ScriptedLLM([looks(2), finish()])
    outcome = run_visit(casual, box, llm, diary, now=NOW, echo=lambda *_: None)
    assert outcome.finished and outcome.pushbacks == 0 and outcome.focus == ""
    assert "focus" not in llm.seen[0][0][1]["content"].lower()
    assert "focus" not in diary.last_entries()[-1]


def test_an_entry_without_a_critical_observation_is_pushed_back_once(setup):
    tester, box, diary, _ = setup
    llm = ScriptedLLM([finish("Everything is running smoothly.", "f1"), finish("Still smooth.", "f2")])
    outcome = run_visit(tester, box, llm, diary, now=NOW, echo=lambda *_: None)
    assert outcome.finished and outcome.pushbacks == 1
    refusal = next(m for m in llm.seen[1][0] if m.get("tool_call_id") == "f1")
    assert "Critical observation:" in refusal["content"]
    assert "Still smooth." in diary.last_entries()[-1]  # the second try saves, whatever it says


def test_the_focus_rotates_with_the_diary(setup):
    tester, box, diary, _ = setup
    seen = []
    for day in range(1, 8):
        llm = ScriptedLLM([finish()])
        seen.append(run_visit(tester, box, llm, diary, now=datetime(2026, 11, day, tzinfo=timezone.utc), echo=lambda *_: None).focus)
    assert seen == ["finances", "roster", "market", "racing", "development", "staff_and_sponsors", "finances"]
    assert "focus: roster, 24.0 h since the last visit" in diary.last_entries(6)[0]


def test_the_visit_opens_with_what_changed_and_saves_the_reading(setup):
    tester, box, diary, _ = setup
    before = {"team": {"id": 7, "name": "Velo", "code": "VTR"}, "season": 3, "week": 5, "balance": 441908}
    diary.append("last visit.\nCritical observation: x", at=datetime(2026, 11, 13, 4, 17, tzinfo=timezone.utc), reading=before)
    now = dict(before, week=7, balance=429927)
    llm = ScriptedLLM([finish()])
    run_visit(tester, box, llm, diary, now=NOW, echo=lambda *_: None, reading=now)
    opening = llm.seen[0][0][1]["content"]
    assert "Your last visit was 8 real hours ago" in opening
    assert "- balance: $441,908 → $429,927 (-$11,981)" in opening
    assert "- Season 3 Week 5 → Season 3 Week 7" in opening
    assert diary.last_reading() == now


def test_a_visit_cut_short_saves_no_reading(setup):
    tester, box, diary, _ = setup
    llm = ScriptedLLM([looks(1)] * 2)
    run_visit(tester, box, llm, diary, max_steps=2, now=NOW, echo=lambda *_: None, reading={"team": None})
    assert diary.last_reading() is None


def test_no_pushback_on_the_last_step_so_the_entry_is_kept(setup):
    _, box, diary, _ = setup
    racer = testers.get("racer")
    llm = ScriptedLLM([looks(1), finish("Short and smooth.")])
    outcome = run_visit(racer, box, llm, diary, max_steps=2, now=NOW, echo=lambda *_: None, reading={"team": None})
    assert outcome.finished and not outcome.cut_short and outcome.pushbacks == 0
    assert "Short and smooth." in diary.last_entries()[-1] and "cut short" not in diary.last_entries()[-1]
    assert diary.last_reading() == {"team": None}


def test_the_observation_must_start_a_line(setup):
    tester, box, diary, _ = setup
    llm = ScriptedLLM([finish("I had no critical observation today.", "f1"), finish("- **Critical observation:** the market is empty.", "f2")])
    outcome = run_visit(tester, box, llm, diary, now=NOW, echo=lambda *_: None)
    assert outcome.pushbacks == 1 and "market is empty" in diary.last_entries()[-1]


def test_a_reading_with_an_unreadable_team_is_not_saved(setup):
    tester, box, diary, _ = setup
    reading = {"team": None, "errors": {"team": "GET /api/accounts/me/ answered 500"}}
    run_visit(tester, box, ScriptedLLM([finish()]), diary, now=NOW, echo=lambda *_: None, reading=reading)
    assert diary.last_reading() is None
