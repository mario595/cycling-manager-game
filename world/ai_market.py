"""How unmanaged teams behave in the rider auction market.

An unmanaged team plays itself: it bids on human listings it has a need for,
and it lists surplus or ageing riders. Everything here is either a pure
decision helper (rider lists in, answer out, no queries) or an orchestrator the
tick calls once per pass — see `specs/ai-transfer-market.md` and
`specs/ai-transfer-market-plan.md` for the reasoning behind each rule.

The helpers are deliberately blind to hidden rider traits: "need" is judged
by `riders.pricing.strength`, which reads visible attributes only, so a human
can never infer a rider's potential from the AI's bids.
"""

from __future__ import annotations

from datetime import timedelta

from riders.models import Rider
from riders.pricing import strength
from teams.services import ROSTER_SIZE

#: Two and a half 4-rider squads, so freshness can rotate at one race a week.
AI_MIN_ROSTER = 10
#: Stops an AI team buying up to ROSTER_CAP. With listing above ROSTER_SIZE,
#: rosters oscillate between ROSTER_SIZE and this number.
AI_MAX_ROSTER = 15
#: "Among its stronger riders for that speciality" means the top two.
AI_NEED_RANK = 2
#: Value's career horizon has fallen well below 1.0 by this age. An AI team
#: would list such a rider straight back out, so it neither buys nor keeps
#: buying them.
AI_AGEING_AGE = 33
#: An AI team never spends more than half its balance on the market.
AI_CUSHION_FRACTION = 0.5
#: Listing is staggered: roughly a quarter of the unmanaged teams list each
#: week, so the market gets a trickle of AI sellers rather than a flood.
AI_LISTING_EVERY_WEEKS = 4
#: Stops the same unsold veteran reappearing every month.
AI_RELIST_COOLDOWN = timedelta(weeks=4)


def _same_speciality(roster: list[Rider], rider: Rider) -> list[Rider]:
    return [own for own in roster if own.speciality == rider.speciality]


def _stronger_than(peers: list[Rider], rider: Rider) -> int:
    level = strength(rider)
    return sum(1 for peer in peers if strength(peer) > level)


def _is_top_of_speciality(roster: list[Rider], rider: Rider) -> bool:
    """Is this rider one of the `AI_NEED_RANK` strongest of their speciality
    on this roster? The buying rule wants the complement of this."""
    return _stronger_than(_same_speciality(roster, rider), rider) < AI_NEED_RANK


def wants_rider(roster: list[Rider], rider: Rider, *, pending_wins: int) -> bool:
    """Does this roster want this rider, ignoring price?

    The budget is the caller's job — it is the one condition that needs a
    balance, and `wants_rider` stays query-free. A thin roster (below
    `AI_MIN_ROSTER`) takes anyone it is allowed to want; otherwise the rider
    has to be among the `AI_NEED_RANK` strongest of their speciality.
    """
    if rider.age >= AI_AGEING_AGE:
        return False
    if len(roster) + pending_wins >= AI_MAX_ROSTER:
        return False
    if len(roster) < AI_MIN_ROSTER:
        return True
    return _stronger_than(_same_speciality(roster, rider), rider) < AI_NEED_RANK


def buyer_rank(roster: list[Rider], rider: Rider, team_pk: int) -> tuple[int, int, int]:
    """Order teams competing for the same listing, lowest first: thin rosters
    ahead of full ones, then the team with fewest riders of that speciality,
    then pk, so the outcome is deterministic."""
    return (
        0 if len(roster) < AI_MIN_ROSTER else 1,
        len(_same_speciality(roster, rider)),
        team_pk,
    )


def pick_listing(roster: list[Rider], candidates: list[Rider]) -> Rider | None:
    """The rider this team should list, or `None` if it should list nobody.

    A roster above `ROSTER_SIZE` is in surplus and sells its weakest
    candidate. Otherwise it sells its oldest ageing rider who is not one of
    the `AI_NEED_RANK` strongest of their speciality — the veterans worth
    keeping are exactly the ones not for sale.
    """
    if not candidates:
        return None
    if len(roster) > ROSTER_SIZE:
        return min(candidates, key=lambda r: (strength(r), -r.age, r.pk))
    qualifying = [
        rider
        for rider in candidates
        if rider.age >= AI_AGEING_AGE and not _is_top_of_speciality(roster, rider)
    ]
    if not qualifying:
        return None
    return min(qualifying, key=lambda r: (-r.age, strength(r), r.pk))


def headroom(balance: int, committed: int) -> int:
    """What this team may still promise the market: half its balance, less
    what its pending wins already ask for, floored at zero. Nothing is
    escrowed, so without that subtraction the same money could be committed
    to several auctions at once."""
    return max(0, int(balance * (1 - AI_CUSHION_FRACTION)) - committed)
