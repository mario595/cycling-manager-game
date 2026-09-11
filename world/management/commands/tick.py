from __future__ import annotations

from django.core.management.base import BaseCommand, CommandError

from world.services import tick as run_tick


class Command(BaseCommand):
    help = "Find and process whatever is due, exactly once. Run hourly from cron in production."

    def handle(self, *args, **options):
        run = run_tick()

        self.stdout.write(
            f"races started {run.races_started}, finished {run.races_finished} | "
            f"capped={run.capped} | "
            f"seasons opened {run.seasons_opened}, closed {run.seasons_closed}"
        )

        if run.error:
            self.stderr.write(run.error)
            raise CommandError("tick completed with errors")
