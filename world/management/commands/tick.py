from __future__ import annotations

from django.core.management.base import BaseCommand, CommandError

from world.models import TickRun
from world.services import advance


class Command(BaseCommand):
    help = (
        "Advance the world once: by elapsed real time (capped) by default, "
        "run hourly from cron in production; or deliberately with --to-next "
        "or --day for development."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--to-next", action="store_true",
            help="Jump to the next scheduled moment.",
        )
        parser.add_argument(
            "--day", nargs="?", const=1, type=int, default=None, metavar="N",
            help="Advance N game days (default 1), processing everything within them.",
        )

    def handle(self, *args, **options):
        to_next = options["to_next"]
        day = options["day"]

        if to_next and day is not None:
            raise CommandError("--to-next and --day are mutually exclusive")

        if day is not None:
            tick = advance(trigger=TickRun.Trigger.DAY, days=day)
        elif to_next:
            tick = advance(trigger=TickRun.Trigger.TO_NEXT, to_next=True)
        else:
            tick = advance(trigger=TickRun.Trigger.CRON)

        self.stdout.write(
            f"clock {tick.from_game_time} -> {tick.to_game_time} | "
            f"races started {tick.races_started}, finished {tick.races_finished} | "
            f"capped={tick.capped}"
        )

        if tick.error:
            self.stderr.write(tick.error)
            raise CommandError("tick completed with errors")
