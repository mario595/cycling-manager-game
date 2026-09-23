from __future__ import annotations

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from riders.generation import generate_roster
from riders.models import Rider
from riders.services import record_initial_snapshots
from teams.models import Team

DEFAULT_RIDERS_PER_TEAM = 12


class Command(BaseCommand):
    help = (
        "Replace the whole rider population with a freshly generated one, "
        "per specs/rider-attributes.md: existing riders, and the race "
        "results and squads that pointed at them, are deleted first. "
        "Destructive — requires --yes."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--yes", action="store_true",
            help="Confirm the destructive delete. Required — refused without it.",
        )
        parser.add_argument(
            "--per-team", type=int, default=DEFAULT_RIDERS_PER_TEAM,
            help=f"Riders generated per team (default {DEFAULT_RIDERS_PER_TEAM}).",
        )

    def handle(self, *args, **options):
        if not options["yes"]:
            raise CommandError(
                "this deletes every rider, race result and squad in the "
                "database — pass --yes to confirm"
            )

        # Imported here, not at module scope: riders/'s library code must
        # never import racing/ (AGENTS.md, riders -> core, teams only). This
        # management command is an entry point, like schedule/'s
        # load_season — see riders/README.md.
        from racing.models import RaceResult, RaceSquad

        per_team = options["per_team"]
        teams = list(Team.objects.all())

        with transaction.atomic():
            result_count = RaceResult.objects.count()
            RaceResult.objects.all().delete()
            squad_count = RaceSquad.objects.count()
            RaceSquad.objects.all().delete()
            rider_count = Rider.objects.count()
            Rider.objects.all().delete()

            created = 0
            for team in teams:
                roster = generate_roster(per_team, team=team)
                created_riders = Rider.objects.bulk_create(roster)
                record_initial_snapshots(created_riders)
                created += len(roster)

        self.stdout.write(
            f"deleted {rider_count} rider(s), {result_count} result(s), "
            f"{squad_count} squad(s)"
        )
        self.stdout.write(f"generated {created} rider(s) across {len(teams)} team(s)")
