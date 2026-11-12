from __future__ import annotations

from datetime import datetime, timezone as dt_timezone

from django.core.management.base import BaseCommand, CommandError
from django.utils.dateparse import parse_datetime

from world.world_setup import (
    WORLD_CALENDAR,
    WORLD_SEASONS,
    WORLD_TEAMS,
    WORLD_TRAINERS,
    WorldError,
    build_world,
    next_monday,
)


def _parse_start(value: str) -> datetime:
    parsed = parse_datetime(f"{value}T00:00:00" if len(value) == 10 else value)
    if parsed is None:
        raise CommandError(f"could not parse --starts-at {value!r}")
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=dt_timezone.utc)
    return parsed


class Command(BaseCommand):
    help = (
        "Build a clean game world in one go: unmanaged, claimable teams, the "
        "trainer pool, and several back-to-back seasons of the world "
        "calendar (seasons/world.json). Refuses if a world already exists "
        "unless --reset wipes it first (accounts are kept). Never creates the "
        "demo account. See world/README.md, *Building a world*."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--starts-at", default=None,
            help="Season 1's opening Monday (YYYY-MM-DD, 00:00 UTC). "
            "Default: the next Monday after the current game time.",
        )
        parser.add_argument("--seasons", type=int, default=WORLD_SEASONS,
                            help=f"Seasons declared up front (default {WORLD_SEASONS}).")
        parser.add_argument("--teams", type=int, default=WORLD_TEAMS,
                            help=f"Unmanaged teams (default {WORLD_TEAMS}).")
        parser.add_argument("--trainers", type=int, default=WORLD_TRAINERS,
                            help=f"Trainers in the pool (default {WORLD_TRAINERS}).")
        parser.add_argument("--calendar", default=str(WORLD_CALENDAR),
                            help="Season file every season is declared from.")
        parser.add_argument(
            "--set-clock", action="store_true",
            help="MockClock only (the accelerated staging world): move the clock "
            "to the start and tick once, so season 1 is open immediately.",
        )
        parser.add_argument(
            "--reset", action="store_true",
            help="Wipe the existing game world first, keeping accounts. Only "
            "where settings.ALLOW_WORLD_RESET is on — never in production.",
        )

    def handle(self, *args, **options):
        from world.services import now

        starts_at = (
            _parse_start(options["starts_at"]) if options["starts_at"] else next_monday(now())
        )
        try:
            build_world(
                starts_at=starts_at,
                seasons=options["seasons"],
                teams=options["teams"],
                trainers=options["trainers"],
                calendar=options["calendar"],
                set_clock=options["set_clock"],
                reset=options["reset"],
                stdout=self.stdout,
            )
        except WorldError as exc:
            raise CommandError(str(exc))
        self.stdout.write(self.style.SUCCESS(
            f"world built: {options['teams']} claimable teams, {options['trainers']} "
            f"trainers, {options['seasons']} season(s) from {starts_at.isoformat()}"
        ))
