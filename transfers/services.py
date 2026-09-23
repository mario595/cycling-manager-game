"""Free agents and the cost of releasing one.

This file opens with the two pure reads the market screen and the Roster's
release-cost column build on. The write paths (sign_free_agent,
release_rider) land in a later work item (specs/free-agents-plan.md, W3).

`transfers/` may import only `riders/` (AGENTS.md). That is why the
claim-cooldown exemption below receives its in-season week count from the
caller instead of counting `schedule/`'s Week rows itself — see Design
decision 2 and 9 in specs/free-agents-plan.md.
"""

from __future__ import annotations

from django.db.models import QuerySet

from riders.models import Rider

from .pricing import severance_fee_for

#: In-season weeks a claimed roster keeps its claim-cooldown exemption: a
#: rider inherited from the most recent claim releases for free while fewer
#: than this many in-season weeks have opened since it. The caller counts
#: the weeks (api/), this module only compares (Design decision 2).
CLAIM_COOLDOWN_WEEKS = 1


def free_agents() -> QuerySet[Rider]:
    """Every rider with no team, ordered by name — the free-agent pool."""
    return Rider.objects.filter(team__isnull=True).order_by("name")


def release_cost_for(team, rider: Rider, *, weeks_opened: int) -> int:
    """What releasing `rider` from `team` would currently charge, without
    changing anything — the figure the roster screen shows per rider,
    including 0. Pure read; safe to call for every rider on a GET.

    A rider inherited from the team's most recent claim is exempt while the
    claim cooldown holds (Design decision 2); everyone else — including a
    rider signed in afterward — pays severance_fee_for. `weeks_opened` is
    the in-season weeks that have opened between `team.managed_since` and
    the relevant boundary (now on a roster GET, `at` on a release), counted
    by the caller.
    """
    if _claim_cooldown_exempt(team, rider, weeks_opened):
        return 0
    return severance_fee_for(rider)


def _claim_cooldown_exempt(team, rider: Rider, weeks_opened: int) -> bool:
    """Whether `rider` is fee-exempt to release *right now*.

    The rider must have joined `team` at the exact instant of its most
    recent claim (`joined_team_at == managed_since`) — the roster claim_team
    generated, not a rider signed in afterward, whose `at` is later — and
    fewer than CLAIM_COOLDOWN_WEEKS in-season weeks must have opened since.
    A team that was never claimed has no cooldown, so nothing is exempt.
    """
    if team.managed_since is None:
        return False
    if rider.joined_team_at != team.managed_since:
        return False
    return weeks_opened < CLAIM_COOLDOWN_WEEKS