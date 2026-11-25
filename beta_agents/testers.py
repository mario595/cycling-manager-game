"""The five beta testers: who they are, how they play, and when they visit.

A tester is due once `period` real hours, less half an hour of slack, have passed
since its last diary entry; a tester with no diary is due at once. The four
regular testers have period 8, about eight game days on the staging clock, and
the minimal-effort tester visits once a real day. The cadence is set by the
free model tier's daily call allowance (specs/archive/beta-agents.md, Cadence).

The rule reads the diary rather than the clock's hour because GitHub runs an
hourly schedule only when it has room: in the first five days it ran 17 of
about 120, hours late and at random, so an exact-hour rule left most testers
with no visit at all. The slack lets a tester go whose last visit started a
few minutes late, behind another tester in the same run, so that on a punctual
schedule the cadence stays at exactly `period` hours.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Callable

DUE_SLACK = timedelta(minutes=30)


@dataclass(frozen=True)
class Tester:
    slug: str
    display_name: str
    period: int
    persona: str
    # A tester that tries to finish before this many tool calls is pushed back
    # once (#159). The minimal-effort tester is exempt: short visits are its
    # persona.
    min_tool_calls: int = 12
    # Whether its visits get a rotating focus area to dig into (#159).
    probes: bool = True

    @property
    def email(self) -> str:
        return f"beta-{self.slug}@velodra.test"

    @property
    def secret_name(self) -> str:
        """The environment variable (and GitHub secret) holding its API key."""
        return f"BETA_KEY_{self.slug.upper()}"

    def is_due(self, last_visit: datetime | None, now: datetime) -> bool:
        if last_visit is None:
            return True
        return now - last_visit >= timedelta(hours=self.period) - DUE_SLACK


TESTERS: tuple[Tester, ...] = (
    Tester(
        slug="youth",
        display_name="Beta Youth Builder",
        period=8,
        persona=(
            "You are a patient youth builder. You believe a team is built from "
            "its own development squad. Open a development squad as soon as you "
            "can afford it, upgrade it when money allows, and decide every "
            "graduate's future: promote the good ones to the roster, list the "
            "rest for auction rather than letting them go for nothing. Keep the "
            "roster young, and sell or release riders who are past their best."
        ),
    ),
    Tester(
        slug="trader",
        display_name="Beta Trader",
        period=8,
        persona=(
            "You are an aggressive trader. Every visit, look at the auction "
            "market and the free-agent pool. Bid on riders who look undervalued, "
            "sign cheap free agents with good attributes, and list riders you "
            "think will sell for more than they are worth to you. Check your "
            "bids from last visit: did you win, were you outbid, did the money "
            "move the way the rules say it should?"
        ),
    ),
    Tester(
        slug="money",
        display_name="Beta Accountant",
        period=8,
        persona=(
            "You are a money-focused manager. Your aim is a healthy balance. "
            "Pick the sponsor offer you think will pay best, keep the wage bill "
            "low, avoid expensive staff, and read the finances ledger carefully "
            "every visit. Check that every payment and charge since your last "
            "visit is one you can explain, and that the balance adds up."
        ),
    ),
    Tester(
        slug="racer",
        display_name="Beta Racer",
        period=8,
        persona=(
            "You are a racer. Results are all that matter to you. Before every "
            "upcoming race, read its course and pick the four riders best "
            "suited to it, with a sensible leader: climbers for the mountains, "
            "sprinters for flat finishes, and rested riders over tired ones. "
            "Set the training focus toward what your team lacks, and read the "
            "results of races that finished since your last visit."
        ),
    ),
    Tester(
        slug="casual",
        display_name="Beta Casual",
        period=24,
        persona=(
            "You are a minimal-effort manager who rarely has time. Visit, check "
            "that nothing is on fire, and leave most things to their defaults. "
            "Do not pick squads yourself: let the game choose them. Only act if "
            "something needs you, such as an unsigned sponsor, money running "
            "out, or a lost team. Keep your visits short."
        ),
        min_tool_calls=0,
        probes=False,
    ),
)


def get(slug: str) -> Tester:
    for tester in TESTERS:
        if tester.slug == slug:
            return tester
    raise KeyError(f"No tester called {slug!r}. Known: {', '.join(t.slug for t in TESTERS)}")


def due(now: datetime, last_visit: Callable[[Tester], datetime | None]) -> list[Tester]:
    """The testers due to visit now, longest-waiting first. `last_visit` gives
    a tester's last diary entry, or None if it has none."""
    waiting = [(t, last_visit(t)) for t in TESTERS]
    ready = [(t, last) for t, last in waiting if t.is_due(last, now)]
    ready.sort(key=lambda pair: pair[1] or datetime.min.replace(tzinfo=now.tzinfo))
    return [t for t, _ in ready]
