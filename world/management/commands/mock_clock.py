from __future__ import annotations

import re
from datetime import timedelta

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone
from django.utils.dateparse import parse_datetime

from racing.models import Race
from world.clocks import MockClock
from world.services import get_clock

_DURATION_RE = re.compile(r"(\d+)([dhm])")


def _parse_duration(value: str) -> timedelta:
    matches = _DURATION_RE.findall(value)
    if not matches:
        raise CommandError(f"could not parse duration: {value!r} (expected e.g. 1d, 6h, 1d6h)")
    unit_to_kwarg = {"d": "days", "h": "hours", "m": "minutes"}
    kwargs: dict[str, int] = {}
    for amount, unit in matches:
        kwarg = unit_to_kwarg[unit]
        kwargs[kwarg] = kwargs.get(kwarg, 0) + int(amount)
    return timedelta(**kwargs)


class Command(BaseCommand):
    help = (
        "Move the developer-controlled mock clock by hand. Only works when "
        "GAME_CLOCK_CLASS is world.clocks.MockClock — never in production."
    )

    def add_arguments(self, parser):
        subparsers = parser.add_subparsers(dest="action", required=True)

        set_parser = subparsers.add_parser("set", help="Set the clock to an exact datetime.")
        set_parser.add_argument("datetime", help="ISO 8601 datetime, e.g. 2027-03-01T09:00")
        set_parser.add_argument(
            "--force", action="store_true",
            help="Allow moving the clock backwards past a finished race.",
        )

        advance_parser = subparsers.add_parser("advance", help="Move the clock forward.")
        group = advance_parser.add_mutually_exclusive_group(required=True)
        group.add_argument(
            "--to-next", action="store_true",
            help="Jump to the next scheduled race's start time.",
        )
        group.add_argument(
            "--by", metavar="DURATION",
            help="Move forward by a duration, e.g. 1d, 6h, 1d6h.",
        )

    def handle(self, *args, **options):
        clock = get_clock()
        if not isinstance(clock, MockClock):
            raise CommandError(
                "mock_clock only works when GAME_CLOCK_CLASS is MockClock; "
                f"current setting: {settings.GAME_CLOCK_CLASS}"
            )

        if options["action"] == "set":
            self._set(clock, options)
        else:
            self._advance(clock, options)

    def _set(self, clock: MockClock, options: dict) -> None:
        parsed = parse_datetime(options["datetime"])
        if parsed is None:
            raise CommandError(f"could not parse datetime: {options['datetime']!r}")
        if timezone.is_naive(parsed):
            parsed = timezone.make_aware(parsed)

        if parsed < clock.now() and not options["force"]:
            rewound_past = Race.objects.filter(
                status=Race.Status.FINISHED, finished_at__gt=parsed,
            ).exists()
            if rewound_past:
                raise CommandError(
                    "refusing to rewind the clock past a finished race; "
                    "pass --force to override"
                )

        clock.set(parsed)
        self.stdout.write(f"clock set to {clock.now()}")

    def _advance(self, clock: MockClock, options: dict) -> None:
        if options["to_next"]:
            clock.advance_to_next_due()
        else:
            clock.advance_by(_parse_duration(options["by"]))
        self.stdout.write(f"clock advanced to {clock.now()}")
