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
    day = first
    while day <= last + timedelta(days=1):
        call_command("tick", stdout=devnull, stderr=devnull)
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


if __name__ == "__main__":
    main()
