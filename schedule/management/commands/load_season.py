from __future__ import annotations

import json
from datetime import timedelta

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from schedule.loaders import SeasonFileError, create_races, parse_season_file
from schedule.models import SEASON_WEEKS, Season, Week


class Command(BaseCommand):
    help = (
        "Declare a season from a JSON file: its number, start and races. "
        "Creates the season, its twelve weeks and any declared races. A "
        "season that has already started can never be touched again."
    )

    def add_arguments(self, parser):
        parser.add_argument("path", help="Path to the season JSON file.")
        parser.add_argument(
            "--replace", action="store_true",
            help="Replace an existing, not-yet-started season with the same number.",
        )

    def handle(self, *args, **options):
        # Imported here, not at module scope: schedule/'s library code
        # (models.py, services.py, loaders.py) must never import racing/ or
        # world/ (AGENTS.md). This management command is an entry point,
        # like world/'s own — see schedule/README.md.
        from racing.models import Race
        from racing.services import create_race
        from world.services import now

        path = options["path"]
        try:
            with open(path) as f:
                data = json.load(f)
        except OSError as exc:
            raise CommandError(f"could not read {path!r}: {exc}")
        except json.JSONDecodeError as exc:
            raise CommandError(f"could not parse {path!r} as JSON: {exc}")

        try:
            declaration = parse_season_file(data)
        except SeasonFileError as exc:
            raise CommandError(str(exc))

        for warning in declaration.warnings:
            self.stdout.write(self.style.WARNING(warning))

        number = declaration.number
        starts_at = declaration.starts_at

        existing = Season.objects.filter(number=number).first()
        if existing is not None:
            if existing.starts_at <= now():
                raise CommandError(
                    f"season {number} has already started and cannot be reconfigured"
                )
            if not options["replace"]:
                raise CommandError(
                    f"season {number} is already declared (starts {existing.starts_at}); "
                    f"pass --replace to replace it"
                )

        ends_at = starts_at + timedelta(weeks=SEASON_WEEKS)
        overlapping = Season.objects.filter(
            starts_at__lt=ends_at, ends_at__gt=starts_at,
        ).exclude(pk=existing.pk if existing else None)
        if overlapping.exists():
            other = overlapping.first()
            raise CommandError(
                f"overlaps season {other.number} ({other.starts_at} to {other.ends_at})"
            )

        highest = Season.objects.exclude(pk=existing.pk if existing else None).order_by(
            "-number"
        ).first()
        if highest is not None and number != highest.number + 1 and existing is None:
            self.stdout.write(
                self.style.WARNING(
                    f"season {number} does not follow directly from the highest "
                    f"declared season ({highest.number})"
                )
            )

        with transaction.atomic():
            if existing is not None:
                # Race.week is PROTECT, so the season's races must go before
                # the season itself — see schedule/README.md, *Declaring a
                # season*. Safe only because the not-yet-started check above
                # already refused any season whose races could be simulated.
                Race.objects.filter(week__season=existing).delete()
                existing.delete()
            season = Season.objects.create(number=number, starts_at=starts_at, ends_at=ends_at)
            weeks = []
            for week_number in range(1, SEASON_WEEKS + 1):
                week_start = starts_at + timedelta(weeks=week_number - 1)
                weeks.append(
                    Week(
                        season=season,
                        number=week_number,
                        starts_at=week_start,
                        ends_at=week_start + timedelta(weeks=1),
                    )
                )
            Week.objects.bulk_create(weeks)
            races = create_races(season, declaration.races, create_race=create_race)

        self.stdout.write(f"season {season.number}: {season.starts_at} to {season.ends_at}")
        for week in weeks:
            self.stdout.write(f"  week {week.number}: {week.starts_at} to {week.ends_at}")

        for race in races:
            distance_km = sum(s["length"] for s in race.course) / 1000
            marker_count = race.markers.count()
            suffix = f", {marker_count} marker{'s' if marker_count != 1 else ''}" if marker_count else ""
            self.stdout.write(
                f"  week {race.week.number} {race.starts_at.strftime('%a %H:%M')} "
                f"— {race.name} ({distance_km:.1f} km{suffix})"
            )
        if races:
            self.stdout.write(f"{len(races)} race(s) declared")
