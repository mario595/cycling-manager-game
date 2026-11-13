"""One visit: the tester reads its diary, plays through the API's tools,
reports what looks wrong, and writes a new diary entry.

A visit is bounded (plan, decision 6): at most `max_steps` model calls, and at
most three reports, whatever the model tries. Errors from the game are results
the model reads; only an unusable model or server stops the visit early, and
then the diary is left alone (decision 8).
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone

from .diary import Diary
from .llm import ChatClient, LLMError
from .prompt import MAX_REPORTS_PER_VISIT, opening_message, system_prompt
from .testers import Tester
from .tools import Toolbox

DEFAULT_MAX_STEPS = 40
DIARY_ENTRIES_READ = 5

FINISH_TOOL = {
    "type": "function",
    "function": {
        "name": "finish_visit",
        "description": (
            "End this visit and save your diary entry, which you will read at the "
            "start of your next visit. Call it once, last."
        ),
        "parameters": {
            "type": "object",
            "properties": {"diary_entry": {"type": "string", "description": "Your diary entry for this visit."}},
            "required": ["diary_entry"],
        },
    },
}

NUDGE = (
    "You stopped without calling `finish_visit`. Call `finish_visit` now with "
    "your diary entry for this visit."
)


@dataclass
class VisitOutcome:
    finished: bool = False
    cut_short: bool = False
    steps: int = 0
    tool_calls: int = 0
    reports_filed: int = 0
    reports_refused: int = 0
    api_errors: int = 0
    diary_entry: str = ""
    error: str = ""
    log: list[str] = field(default_factory=list)

    def summary(self) -> str:
        return (
            f"steps={self.steps} tool_calls={self.tool_calls} reports={self.reports_filed} "
            f"refused_reports={self.reports_refused} api_errors={self.api_errors} "
            f"finished={self.finished} cut_short={self.cut_short}"
        )


def run_visit(
    tester: Tester,
    toolbox: Toolbox,
    llm: ChatClient,
    diary: Diary,
    max_steps: int = DEFAULT_MAX_STEPS,
    now: datetime | None = None,
    echo=print,
) -> VisitOutcome:
    now = now or datetime.now(timezone.utc)
    outcome = VisitOutcome()
    tools = toolbox.tools() + [FINISH_TOOL]
    messages: list[dict] = [
        {"role": "system", "content": system_prompt(tester)},
        {"role": "user", "content": opening_message(diary.last_entries(DIARY_ENTRIES_READ), now.strftime("%Y-%m-%d %H:%M UTC"))},
    ]
    nudged = False

    def note(line: str) -> None:
        outcome.log.append(line)
        echo(line)

    while outcome.steps < max_steps and not outcome.finished:
        outcome.steps += 1
        try:
            message = llm.chat(messages, tools)
        except LLMError as error:
            if outcome.steps == 1:
                raise  # nothing happened yet: skip the visit, diary untouched
            outcome.error = str(error)
            note(f"[{tester.slug}] model failed mid-visit: {error}")
            break
        calls = message.get("tool_calls") or []
        messages.append(_assistant_message(message, calls))
        if message.get("content"):
            note(f"[{tester.slug}] says: {_one_line(message['content'])}")
        if not calls:
            if nudged:
                break
            nudged = True
            messages.append({"role": "user", "content": NUDGE})
            continue
        for call in calls:
            name = call.get("function", {}).get("name", "")
            arguments = _arguments(call)
            outcome.tool_calls += 1
            if name == "finish_visit":
                outcome.finished = True
                outcome.diary_entry = str(arguments.get("diary_entry", "")).strip()
                result = json.dumps({"saved": True})
                note(f"[{tester.slug}] finish_visit")
            elif name == "report_a_problem" and outcome.reports_filed >= MAX_REPORTS_PER_VISIT:
                outcome.reports_refused += 1
                result = json.dumps(
                    {"error": f"You have already filed {MAX_REPORTS_PER_VISIT} reports this visit. Note it in your diary and report it next visit."}
                )
                note(f"[{tester.slug}] report refused (cap)")
            else:
                result = toolbox.execute(name, arguments)
                status = _status(result)
                if name == "report_a_problem" and status == 201:
                    outcome.reports_filed += 1
                if status is not None and status >= 500:
                    outcome.api_errors += 1
                note(f"[{tester.slug}] {name} {json.dumps(arguments, ensure_ascii=False)[:200]} -> {status}")
            messages.append({"role": "tool", "tool_call_id": call.get("id", ""), "name": name, "content": result})
        # Anything the model asked for after finish_visit has still been answered,
        # so the transcript stays well-formed; the loop ends here.

    if not outcome.finished:
        outcome.cut_short = True
        if outcome.error:
            reason = f"the model failed ({outcome.error[:200]})"
        elif outcome.steps >= max_steps:
            reason = "it ran out of steps"
        else:
            reason = "the model stopped without writing one"
        outcome.diary_entry = (
            f"(Written by the harness: this visit ended before I wrote my diary entry, because {reason}, "
            f"after {outcome.steps} steps and {outcome.tool_calls} tool calls. "
            "Start the next visit by checking the team's state from scratch.)"
        )
    diary.append(_with_footer(outcome), at=now)
    note(f"[{tester.slug}] visit over: {outcome.summary()}")
    return outcome


def _with_footer(outcome: VisitOutcome) -> str:
    return (
        f"{outcome.diary_entry}\n\n"
        f"_Visit stats: {outcome.tool_calls} tool calls, {outcome.reports_filed} reports filed"
        + (", cut short" if outcome.cut_short else "")
        + "._"
    )


def _assistant_message(message: dict, calls: list[dict]) -> dict:
    out: dict = {"role": "assistant", "content": message.get("content") or ""}
    if calls:
        out["tool_calls"] = [
            {
                "id": call.get("id", ""),
                "type": "function",
                "function": {
                    "name": call.get("function", {}).get("name", ""),
                    "arguments": call.get("function", {}).get("arguments", "{}"),
                },
            }
            for call in calls
        ]
    return out


def _arguments(call: dict) -> dict:
    raw = call.get("function", {}).get("arguments", "{}")
    if isinstance(raw, dict):
        return raw
    try:
        parsed = json.loads(raw or "{}")
    except json.JSONDecodeError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _status(result: str) -> int | None:
    """The HTTP status at the head of a tool result (which may be cut)."""
    match = re.match(r'\{"status": (\d+)', result)
    return int(match.group(1)) if match else None


def _one_line(text: str, limit: int = 300) -> str:
    flat = " ".join(str(text).split())
    return flat if len(flat) <= limit else flat[:limit] + "..."
