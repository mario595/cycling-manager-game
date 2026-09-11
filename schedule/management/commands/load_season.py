from __future__ import annotations

import json
from datetime import time, timedelta, timezone as dt_timezone

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone
from django.utils.dateparse import parse_datetime

from schedule.models import SEASON_WEEKS, Season, Week

_KNOWN_KEYS = {"number", "starts_at"}


class Command(BaseCommand):
    help = (
        "Declare a season from a JSON file: its number and start. Creates "
        "the season and its twelve weeks. A season that has already "
        "started can never be touched again."
    )

    def add_arguments(self, parser):
        parser.add_argument("path", help="Path to the season JSON file.")
        parser.add_argument(
            "--replace", action="store_true",
            help="Replace an existing, not-yet-started season with the same number.",
        )

    def handle(self, *args, **options):
        # Imported here, not at module scope: schedule/'s library code
        # (models.py, services.py) must never import world/ (AGENTS.md).
        # This management command is an entry point, like world/'s own —
        # see schedule/README.md.
        from world.services import now

        path = options["path"]
        try:
            with open(path) as f:
                data = json.load(f)
        except OSError as exc:
            raise CommandError(f"could not read {path!r}: {exc}")
        except json.JSONDecodeError as exc:
            raise CommandError(f"could not parse {path!r} as JSON: {exc}")

        unknown_keys = set(data) - _KNOWN_KEYS
        if unknown_keys:
            self.stdout.write(
                self.style.WARNING(f"ignoring unknown key(s): {', '.join(sorted(unknown_keys))}")
            )

        number = data.get("number")
        if not isinstance(number, int) or number < 1:
            raise CommandError("'number' must be an integer >= 1")

        raw_starts_at = data.get("starts_at")
        if not isinstance(raw_starts_at, str):
            raise CommandError("'starts_at' is required and must be an ISO 8601 string")
        starts_at = parse_datetime(raw_starts_at)
        if starts_at is None:
            raise CommandError(f"could not parse 'starts_at': {raw_starts_at!r}")
        if timezone.is_naive(starts_at):
            starts_at = timezone.make_aware(starts_at, dt_timezone.utc)

        starts_at_utc = timezone.localtime(starts_at, dt_timezone.utc)
        if starts_at_utc.weekday() != 0 or starts_at_utc.time() != time(0, 0, 0):
            nearest_monday = starts_at_utc.date() - timedelta(days=starts_at_utc.weekday())
            raise CommandError(
                f"'starts_at' must be a Monday at 00:00:00 UTC; "
                f"got {starts_at_utc.isoformat()}, nearest Monday is {nearest_monday}"
            )

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

        self.stdout.write(f"season {season.number}: {season.starts_at} to {season.ends_at}")
        for week in weeks:
            self.stdout.write(f"  week {week.number}: {week.starts_at} to {week.ends_at}")
