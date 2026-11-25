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

from . import snapshot
from .diary import Diary
from .llm import ChatClient, LLMError
from .prompt import MAX_REPORTS_PER_VISIT, focus_for, opening_message, system_prompt
from .testers import Tester
from .tools import Toolbox

DEFAULT_MAX_STEPS = 30
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

OBSERVATION_MARK = "critical observation"

EARLY_FINISH = (
    "Not saved: you have made only {calls} tool calls this visit, which is not "
    "enough to have looked properly. Keep going{focus}: cross-check what you "
    "see against the guide, the ledger and other endpoints, and report what "
    "you cannot explain. Then call `finish_visit` again."
)

NO_OBSERVATION = (
    "Not saved: your diary entry has no line starting `Critical observation:`. "
    "Name at least one thing this visit that was confusing, surprising, "
    "missing or suspicious (\"everything is fine\" does not count), and call "
    "`finish_visit` again with the whole entry."
)

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
    pushbacks: int = 0
    focus: str = ""
    hours_since: float | None = None
    diary_entry: str = ""
    error: str = ""
    log: list[str] = field(default_factory=list)

    def summary(self) -> str:
        return (
            f"steps={self.steps} tool_calls={self.tool_calls} reports={self.reports_filed} "
            f"refused_reports={self.reports_refused} api_errors={self.api_errors} "
            f"pushbacks={self.pushbacks} focus={self.focus or '-'} "
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
    reading: dict | None = None,
) -> VisitOutcome:
    """`reading` is the harness's reading of the team (snapshot.take), taken
    before the visit. It opens the visit with what changed since the last
    reading, and is saved with the new entry for the next visit."""
    now = now or datetime.now(timezone.utc)
    outcome = VisitOutcome()
    last_visit = diary.last_visit_at()
    if last_visit is not None:
        outcome.hours_since = (now - last_visit).total_seconds() / 3600
    focus = focus_for(tester, diary.entry_count())
    outcome.focus = focus[0] if focus else ""
    changes = snapshot.describe_changes(diary.last_reading(), reading) if reading is not None else None
    tools = toolbox.tools() + [FINISH_TOOL]
    messages: list[dict] = [
        {"role": "system", "content": system_prompt(tester)},
        {
            "role": "user",
            "content": opening_message(
                diary.last_entries(DIARY_ENTRIES_READ),
                now.strftime("%Y-%m-%d %H:%M UTC"),
                changes=changes,
                focus=focus,
                hours_since=outcome.hours_since,
            ),
        },
    ]
    nudged = False
    pushed_early = pushed_observation = False

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
            entry = str(arguments.get("diary_entry", "")) if name == "finish_visit" else ""
            if name == "finish_visit" and outcome.finished:
                result = json.dumps({"saved": True})  # a second call in the same turn
            elif name == "finish_visit" and not pushed_early and outcome.tool_calls - 1 < tester.min_tool_calls:
                pushed_early = True
                outcome.pushbacks += 1
                result = json.dumps(
                    {
                        "saved": False,
                        "error": EARLY_FINISH.format(
                            calls=outcome.tool_calls - 1, focus=f" on your focus area, {focus[0]}" if focus else ""
                        ),
                    }
                )
                note(f"[{tester.slug}] finish_visit pushed back: only {outcome.tool_calls - 1} tool calls")
            elif name == "finish_visit" and not pushed_observation and OBSERVATION_MARK not in entry.lower():
                pushed_observation = True
                outcome.pushbacks += 1
                result = json.dumps({"saved": False, "error": NO_OBSERVATION})
                note(f"[{tester.slug}] finish_visit pushed back: no critical observation")
            elif name == "finish_visit":
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
    # A visit cut short never accounted for the changes, so it saves no
    # reading: the next visit compares with nothing rather than half a story.
    diary.append(_with_footer(outcome), at=now, reading=reading if outcome.finished else None)
    note(f"[{tester.slug}] visit over: {outcome.summary()}")
    return outcome


def _with_footer(outcome: VisitOutcome) -> str:
    return (
        f"{outcome.diary_entry}\n\n"
        f"_Visit stats: {outcome.tool_calls} tool calls, {outcome.reports_filed} reports filed"
        + (f", focus: {outcome.focus}" if outcome.focus else "")
        + (f", {outcome.hours_since:.1f} h since the last visit" if outcome.hours_since is not None else "")
        + (", cut short" if outcome.cut_short else "")
        + "._"
    )


def _assistant_message(message: dict, calls: list[dict]) -> dict:
    """The model's turn as it goes back into the history.

    Each tool call is echoed with every field the provider sent, not only the
    OpenAI ones: Gemini 3 attaches a thought signature to its calls
    (`extra_content.google.thought_signature`) and answers 400 to a history
    that drops it.
    """
    out: dict = {"role": "assistant", "content": message.get("content") or ""}
    if calls:
        echoed = []
        for call in calls:
            function = call.get("function", {})
            arguments = function.get("arguments", "{}")
            if not isinstance(arguments, str):
                arguments = json.dumps(arguments)
            echoed.append(
                {
                    **call,
                    "id": call.get("id", ""),
                    "type": "function",
                    "function": {**function, "name": function.get("name", ""), "arguments": arguments},
                }
            )
        out["tool_calls"] = echoed
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
