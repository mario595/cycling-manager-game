from __future__ import annotations

from django.core.management.base import BaseCommand, CommandError

from world.world_setup import WORLD_CALENDAR, WorldError, add_season


class Command(BaseCommand):
    help = (
        "Declare the world calendar as the next season, starting exactly where "
        "the last declared season ends. Run it before a world runs out of "
        "calendar. See world/README.md, *Building a world*."
    )

    def add_arguments(self, parser):
        parser.add_argument("--calendar", default=str(WORLD_CALENDAR),
                            help="Season file to declare (default the world calendar).")

    def handle(self, *args, **options):
        try:
            number = add_season(calendar=options["calendar"], stdout=self.stdout)
        except WorldError as exc:
            raise CommandError(str(exc))
        self.stdout.write(self.style.SUCCESS(f"season {number} declared"))
