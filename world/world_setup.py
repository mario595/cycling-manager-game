"""Building, extending and wiping a whole game world (#139).

`seed_world` and `add_season` are thin wrappers over this module. It lives
in `world/` because building a world is orchestration across every domain
— teams, staff, schedule, racing, economy — and `world/` is the one app
allowed to know about all of them (AGENTS.md, *Dependency direction*).

Each domain still owns its own seeding: this module calls the existing
`seed_teams`, `seed_trainers` and `load_season` commands rather than
re-implementing them, so a change to how a team is seeded reaches a built
world with no change here. See world/README.md, *Building a world*.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone as dt_timezone
from pathlib import Path

from django.apps import apps
from django.conf import settings
from django.core.management import call_command
from django.db import connection, transaction

#: The world calendar every season of a built world is declared from
#: (specs/archive/beta-world.md, In scope 1). One file, re-anchored per season.
WORLD_CALENDAR = Path(settings.BASE_DIR) / "seasons" / "world.json"

#: World size, settled in specs/archive/beta-world.md, *Decisions taken*: the same
#: in staging and production. Every team is left claimable.
WORLD_TEAMS = 16
#: Bigger than staff.generation.INITIAL_POOL_SIZE (12): with 16 unmanaged
#: teams each hiring the cheapest trainer they can afford
#: (world/ai_management.py), a pool of 12 runs dry before a human arrives.
WORLD_TRAINERS = 24
#: Seasons declared up front — about two weeks of the accelerated staging
#: clock. `add_season` appends more.
WORLD_SEASONS = 4

#: The apps whose rows make up "the game world" a wipe removes. Accounts
#: (and Django's own auth, sessions, admin) are deliberately absent: a
#: wipe keeps every user (specs/archive/beta-world.md, In scope 9). A new game app
#: is **not** wiped until it is added here — the safe default for an app
#: that might hold something an operator wants to keep — **but only if it
#: holds no database foreign-key constraint into a wiped table**, since
#: TRUNCATE … CASCADE empties any such table whatever the app. `feedback`
#: survives because `Report.team` is declared with `db_constraint=False`,
#: and `wipe_world` clears that column before truncating (#131).
WORLD_APPS = (
    "teams",
    "riders",
    "transfers",
    "staff",
    "economy",
    "schedule",
    "racing",
    "competitions",
    "world",
)
#: Kept through a wipe: the mock clock's one row is the staging world's
#: notion of "now", which `seed_world --set-clock` moves deliberately.
KEPT_MODELS = {("world", "gameclock")}


class WorldError(Exception):
    """A world operation refused: an existing world, a disallowed wipe, a
    start date that is not a Monday. Turned into a CommandError."""


def world_exists() -> bool:
    """Whether anything a world is built from is already there."""
    from schedule.models import Season
    from staff.models import Trainer
    from teams.models import Team

    return Team.objects.exists() or Season.objects.exists() or Trainer.objects.exists()


def next_monday(after: datetime) -> datetime:
    """The first Monday 00:00 UTC strictly after `after`."""
    day = after.astimezone(dt_timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    days_ahead = (7 - day.weekday()) % 7 or 7
    return day + timedelta(days=days_ahead)


def check_season_start(starts_at: datetime) -> None:
    """A season starts on a Monday at 00:00:00 UTC (schedule/README.md, *The
    week boundary*). Checked up front so seed_world refuses before it has
    created anything, rather than half-way through, on the first season."""
    utc = starts_at.astimezone(dt_timezone.utc)
    if utc.weekday() != 0 or (utc.hour, utc.minute, utc.second, utc.microsecond) != (0, 0, 0, 0):
        raise WorldError(f"a season must start on a Monday at 00:00 UTC, got {utc.isoformat()}")


def wipe_world() -> dict[str, int]:
    """Delete the whole game world, keeping every account.

    Refuses unless `settings.ALLOW_WORLD_RESET` is true: dev.py allows it,
    staging.py (#129) must say so explicitly, and prod.py never does — so a
    production database can only be wiped by someone editing settings.

    Race log files are deleted from storage first, since truncating
    `RaceLog` would otherwise orphan them on disk. Then every table of
    `WORLD_APPS` is truncated in one statement with CASCADE — the models
    hold PROTECT foreign keys in several directions (a race's week, a
    stage's tour), which an ORM delete would have to unpick in order, and
    that order would silently go stale with every new model. Returns the
    row count of each table before the wipe, for the operator's log.
    """
    if not getattr(settings, "ALLOW_WORLD_RESET", False):
        raise WorldError(
            "wiping the world is not allowed here: settings.ALLOW_WORLD_RESET is off "
            "(it is never on in production)"
        )

    from feedback.models import Report
    from racing.models import RaceLog

    for log in RaceLog.objects.exclude(file=""):
        log.file.delete(save=False)

    models = [
        model
        for app in WORLD_APPS
        for model in apps.get_app_config(app).get_models()
        if (model._meta.app_label, model._meta.model_name) not in KEPT_MODELS
        and not model._meta.proxy
        and model._meta.managed
    ]
    counts = {model._meta.label: model.objects.count() for model in models}
    tables = ", ".join(connection.ops.quote_name(m._meta.db_table) for m in models)
    with transaction.atomic(), connection.cursor() as cursor:
        # Django's foreign keys are DEFERRABLE INITIALLY DEFERRED, and
        # Postgres refuses to truncate a table with deferred checks still
        # pending in the transaction — which there are whenever the wipe
        # runs inside one that already wrote (a test, or build_world's own).
        # Firing them now is harmless: they are checks on rows about to go.
        cursor.execute("SET CONSTRAINTS ALL IMMEDIATE")
        # Reports outlive the world (#131). Their team link carries no
        # database constraint, so the CASCADE below leaves them alone; it is
        # cleared here so RESTART IDENTITY cannot pair a report with an
        # unrelated new team. team_name keeps the snapshot.
        Report.objects.exclude(team=None).update(team=None)
        cursor.execute(f"TRUNCATE {tables} RESTART IDENTITY CASCADE")
    return counts


def add_season(*, calendar: Path = WORLD_CALENDAR, stdout=None) -> int:
    """Declare the world calendar as the next season, starting where the
    last declared one ends. Returns the new season's number."""
    from schedule.models import Season

    last = Season.objects.order_by("-number").first()
    if last is None:
        raise WorldError("no season is declared yet — build the world with seed_world first")
    number = last.number + 1
    call_command(
        "load_season", str(calendar),
        number=number, starts_at=last.ends_at.isoformat(),
        stdout=stdout,
    )
    return number


def build_world(
    *,
    starts_at: datetime,
    seasons: int = WORLD_SEASONS,
    teams: int = WORLD_TEAMS,
    trainers: int = WORLD_TRAINERS,
    calendar: Path = WORLD_CALENDAR,
    set_clock: bool = False,
    reset: bool = False,
    stdout=None,
) -> None:
    """Build a clean world: teams, trainers, then `seasons` back-to-back
    seasons of the calendar from `starts_at`.

    The order is the one AGENTS.md (*Seeding a world for testing*) warns
    about: teams before seasons, so no team gets a sponsor offer round when
    it is created — and the round then comes from the tick that opens
    season 1, exactly as it will for every later season. With `set_clock`
    (the accelerated staging world, MockClock only) the clock is moved to
    `starts_at` **before** anything is seeded, so every opening ledger entry
    is stamped in game time, and one tick then opens season 1 straight away.

    Never creates a user — the demo account belongs to development only.
    """
    from world.clocks import MockClock
    from world.services import get_clock, tick

    check_season_start(starts_at)
    if seasons < 1:
        raise WorldError("a world needs at least one season")
    clock = get_clock()
    if set_clock and not isinstance(clock, MockClock):
        raise WorldError(
            "--set-clock needs GAME_CLOCK_CLASS = world.clocks.MockClock; "
            "a world on the real clock simply opens on its start date"
        )
    from schedule.models import Season

    # One transaction for the seeding, so a failure (a broken calendar file,
    # say) leaves no half-built world behind. The tick stays outside it: it
    # manages its own transactions and claims.
    with transaction.atomic():
        if reset:
            wipe_world()
        elif world_exists():
            raise WorldError(
                "a world already exists (teams, trainers or seasons are declared); "
                "pass --reset to wipe it first"
            )

        if set_clock:
            from world.models import GameClock

            GameClock.load()  # MockClock.set expects the row to exist
            clock.set(starts_at)

        call_command("seed_teams", count=teams, stdout=stdout)
        call_command("seed_trainers", count=trainers, stdout=stdout)
        season_start = starts_at
        for number in range(1, seasons + 1):
            call_command(
                "load_season", str(calendar),
                number=number, starts_at=season_start.isoformat(),
                stdout=stdout,
            )
            season_start = Season.objects.get(number=number).ends_at

    if set_clock:
        tick()
