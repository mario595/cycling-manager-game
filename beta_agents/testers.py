"""The five beta testers: who they are, how they play, and when they visit.

A tester visits when `hour % period == offset`, the hour being the current UTC
hour. The four regular testers share period 4 with offsets 0-3, so exactly one
of them visits each hour, and each visits every four real hours (about four
game days on the staging clock). The minimal-effort tester visits once a real
day (specs/archive/beta-agents.md, Cadence).
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Tester:
    slug: str
    display_name: str
    period: int
    offset: int
    persona: str

    @property
    def email(self) -> str:
        return f"beta-{self.slug}@velodra.test"

    @property
    def secret_name(self) -> str:
        """The environment variable (and GitHub secret) holding its API key."""
        return f"BETA_KEY_{self.slug.upper()}"

    def is_due(self, hour: int) -> bool:
        return hour % self.period == self.offset


TESTERS: tuple[Tester, ...] = (
    Tester(
        slug="youth",
        display_name="Beta Youth Builder",
        period=4,
        offset=0,
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
        period=4,
        offset=1,
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
        period=4,
        offset=2,
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
        period=4,
        offset=3,
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
        offset=2,
        persona=(
            "You are a minimal-effort manager who rarely has time. Visit, check "
            "that nothing is on fire, and leave most things to their defaults. "
            "Do not pick squads yourself: let the game choose them. Only act if "
            "something needs you, such as an unsigned sponsor, money running "
            "out, or a lost team. Keep your visits short."
        ),
    ),
)


def get(slug: str) -> Tester:
    for tester in TESTERS:
        if tester.slug == slug:
            return tester
    raise KeyError(f"No tester called {slug!r}. Known: {', '.join(t.slug for t in TESTERS)}")


def due(hour: int) -> list[Tester]:
    """The testers due to visit at this UTC hour, in a fixed order."""
    return [t for t in TESTERS if t.is_due(hour)]
