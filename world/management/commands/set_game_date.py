from __future__ import annotations

from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone
from django.utils.dateparse import parse_datetime

from racing.models import Race
from world.models import GameClock


class Command(BaseCommand):
    help = (
        "Set the world's current game date and time directly. Development "
        "and admin only: there is no player-facing way to move the clock."
    )

    def add_arguments(self, parser):
        parser.add_argument("datetime", help="ISO 8601 datetime, e.g. 2027-03-01T09:00")
        parser.add_argument(
            "--force", action="store_true",
            help="Allow moving the clock backwards past a finished race.",
        )

    def handle(self, *args, **options):
        parsed = parse_datetime(options["datetime"])
        if parsed is None:
            raise CommandError(f"could not parse datetime: {options['datetime']!r}")
        if timezone.is_naive(parsed):
            parsed = timezone.make_aware(parsed)

        clock = GameClock.load()

        if parsed < clock.current and not options["force"]:
            rewound_past = Race.objects.filter(
                status=Race.Status.FINISHED, finished_at__gt=parsed,
            ).exists()
            if rewound_past:
                raise CommandError(
                    "refusing to rewind the clock past a finished race; "
                    "pass --force to override"
                )

        clock.current = parsed
        clock.last_advanced_at = timezone.now()
        clock.save(update_fields=["current", "last_advanced_at"])

        self.stdout.write(f"clock set to {clock.current}")
