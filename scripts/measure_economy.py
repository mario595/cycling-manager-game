"""Play two seeded seasons on the mock clock and print what the economy did.

This is the measurement behind `economy/README.md`, *Balance targets*: it
seeds a fresh world (the same seed commands AGENTS.md lists), ticks it a
day at a time through seasons 1 and 2, and prints, for the unmanaged teams,
the average of every ledger kind per season plus the spread of season-2
net results by quarter of the field.

It **drops and recreates** this checkout's development database first, so
run it only in a checkout whose dev data you do not mind losing:

    .venv/bin/python scripts/measure_economy.py

Season 2 is the steady state (season 1 carries one-off costs such as a
trainer's hire fee), so it is the figure the targets are checked against.

Just before season 2 opens it also **claims a team** with a throwaway
account, the way a player joining late would (#156), signs that team's
steady sponsor once the season opens and otherwise leaves it alone, and
prints its season beside the unmanaged field's. A claimed team should land
in the middle of the field; one in the bottom quarter means claiming has
started handing out weaker squads than the world's again.
"""

from __future__ import annotations

import os
import sys
from collections import defaultdict
from datetime import timedelta
from pathlib import Path

#: Opening grants, not a season's flow.
OPENING_KINDS = ("starting_balance", "takeover")

ROOT = Path(__file__).resolve().parent.parent


def _reset_database() -> None:
    import psycopg2

    sys.path.insert(0, str(ROOT))
    from config.worktree import database_name

    name = database_name()
    conn = psycopg2.connect(
        host=os.environ.get("POSTGRES_HOST", "127.0.0.1"),
        port=os.environ.get("POSTGRES_PORT", "5433"),
        user=os.environ.get("POSTGRES_USER", "cycling"),
        password=os.environ.get("POSTGRES_PASSWORD", "cycling"),
        dbname="postgres",
    )
    conn.autocommit = True
    cur = conn.cursor()
    cur.execute(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)')
    cur.execute(f'CREATE DATABASE "{name}"')
    conn.close()


def main() -> None:
    os.environ["GAME_CLOCK_CLASS"] = "world.clocks.MockClock"
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.dev")
    os.chdir(ROOT)
    _reset_database()

    import django

    sys.path.insert(0, str(ROOT))
    django.setup()

    from django.core.management import call_command
    from django.db.models import Sum

    from economy.models import LedgerEntry
    from schedule.models import Season
    from teams.models import Team

    quiet = {"verbosity": 0}
    call_command("migrate", **quiet)
    call_command("seed_user", **quiet)
    call_command("seed_teams", **quiet)
    call_command("seed_trainers", **quiet)
    call_command("load_season", "seasons/season-1.example.json", **quiet)
    call_command("load_season", "seasons/season-2.example.json", **quiet)

    seasons = list(Season.objects.order_by("number"))
    first = seasons[0].starts_at
    last = seasons[-1].ends_at

    call_command("mock_clock", "set", first.isoformat(), **quiet)
    devnull = open(os.devnull, "w")
    measured = seasons[-1]
    claimed = None
    sponsored = False
    day = first
    while day <= last + timedelta(days=1):
        if claimed is None and day >= measured.starts_at:
            claimed, claim_report = _claim_a_team(day)
        call_command("tick", stdout=devnull, stderr=devnull)
        if claimed is not None and not sponsored:
            sponsored = _sign_steady_sponsor(claimed, measured, day)
        day += timedelta(days=1)
        call_command("mock_clock", "advance", "--by", "1d", stdout=devnull)

    teams = list(Team.objects.filter(manager__isnull=True))
    print(f"{len(teams)} unmanaged teams\n")
    nets_by_season: dict[int, list[int]] = {}
    for season in seasons:
        in_season = LedgerEntry.objects.filter(
            team__in=teams,
            occurred_at__gte=season.starts_at,
            occurred_at__lt=season.ends_at,
        ).exclude(kind__in=OPENING_KINDS)
        rows = in_season.values("kind").annotate(total=Sum("amount"))
        totals: dict[str, int] = defaultdict(int)
        for row in rows:
            totals[row["kind"]] += row["total"]
        weeks = season.weeks.count()
        print(f"Season {season.number} ({weeks} weeks), average per team:")
        for kind, total in sorted(totals.items(), key=lambda kv: -kv[1]):
            avg = total / len(teams)
            print(f"  {kind:<24} {avg:>12,.0f}   ({avg / weeks:>9,.0f}/wk)")
        net = sum(v for k, v in totals.items() if k != "transfer_fee") / len(teams)
        print(f"  {"NET (excl. transfers)":<24} {net:>12,.0f}   ({net / weeks:>9,.0f}/wk)\n")

        per_team = []
        for team in teams:
            own = in_season.exclude(kind="transfer_fee").filter(team=team).aggregate(s=Sum("amount"))["s"] or 0
            per_team.append(own)
        nets_by_season[season.number] = sorted(per_team)

    steady = nets_by_season[seasons[-1].number]
    q = max(1, len(steady) // 4)
    print(f"Season {seasons[-1].number} net per team, by quarter of the field:")
    print(f"  bottom quarter average {sum(steady[:q]) / q:>12,.0f}")
    print(f"  median                 {steady[len(steady) // 2]:>12,.0f}")
    print(f"  top quarter average    {sum(steady[-q:]) / q:>12,.0f}")
    print(f"  worst / best           {steady[0]:>12,.0f} / {steady[-1]:,.0f}")

    from economy.services import balance_for

    balances = sorted(balance_for(t) for t in teams)
    print(f"\nBalances after season {seasons[-1].number}: "
          f"lowest {balances[0]:,}, median {balances[len(balances) // 2]:,}, "
          f"highest {balances[-1]:,}")

    claimed_net = LedgerEntry.objects.filter(
        team=claimed,
        occurred_at__gte=measured.starts_at,
        occurred_at__lt=measured.ends_at,
    ).exclude(kind__in=OPENING_KINDS + ("transfer_fee",)).aggregate(s=Sum("amount"))["s"] or 0
    beaten = sum(1 for net in steady if net < claimed_net)
    print(f"\nClaimed team (claimed just before season {measured.number} opened):")
    print(f"  {claim_report}")
    print(f"  steady sponsor signed  {'yes' if sponsored else 'NO'}")
    print(f"  season {measured.number} net         {claimed_net:>12,.0f}"
          f"   (ahead of {beaten} of {len(steady)} unmanaged teams)")


def _claim_a_team(at):
    """Claim a team the way ClaimTeamView does, with a throwaway account.

    Returns the team and a line describing where its squad sat in the field
    at the claim. The account never stamps last_seen_at, which exempts it
    from the inactivity release."""
    from accounts.models import User
    from django.db import transaction
    from riders.models import Rider
    from teams.models import Team
    from teams.services import claim_team, squad_strength
    from transfers.services import cancel_listings, withdraw_bids

    user = User.objects.create_user(email="measure-claim@example.com", password="unused-x9")
    with transaction.atomic():
        team = claim_team(user, name="Measured Claim", code="MSR", at=at)
        withdraw_bids(team, at=at)
        cancel_listings(team, at=at)
    scores = sorted(
        squad_strength(list(Rider.objects.filter(team=t))) for t in Team.objects.all()
    )
    own = squad_strength(list(Rider.objects.filter(team=team)))
    rank = sum(1 for score in scores if score > own) + 1
    return team, (
        f"squad strength {own:.1f}, rank {rank} of {len(scores)} "
        f"(field {scores[0]:.1f} to {scores[-1]:.1f}), {team.riders.count()} riders"
    )


def _sign_steady_sponsor(team, season, at) -> bool:
    """Sign `season`'s steady offer for `team`, as the AI does for its own
    teams. False until the season has opened and the offer exists."""
    from economy.models import SponsorOffer
    from economy.services import active_contract, ensure_offer_round, sign_offer
    from world.ai_management import AI_SPONSOR_PROFILE

    if at < season.starts_at:
        return False
    if active_contract(team, season) is not None:
        return True
    ensure_offer_round(team, season, at=at)
    offer = SponsorOffer.objects.filter(team=team, season=season, profile=AI_SPONSOR_PROFILE).first()
    if offer is None:
        return False
    sign_offer(team, offer.pk, at=at)
    return True


if __name__ == "__main__":
    main()
