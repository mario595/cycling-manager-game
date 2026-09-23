from __future__ import annotations

from django.core.management.base import BaseCommand, CommandError

from teams.models import ManagerialSpell, Team
from teams.services import release_team


class Command(BaseCommand):
    help = (
        "Return a managed team to the unmanaged pool by hand. Until #63 "
        "(inactivity) or #27 (insolvency) exist, this is the only way to "
        "call release_team outside a test."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "team", help="Team pk, or exact team name if not all digits."
        )
        parser.add_argument(
            "--reason",
            choices=ManagerialSpell.Reason.values,
            default=ManagerialSpell.Reason.ADMIN,
            help="Reason recorded on the spell (default: admin).",
        )

    def handle(self, *args, **options):
        identifier = options["team"]
        if identifier.isdigit():
            team = Team.objects.filter(pk=int(identifier)).first()
        else:
            team = Team.objects.filter(name=identifier).first()
        if team is None:
            raise CommandError(f"no team matching {identifier!r}")

        # Imported here, not at module scope: teams/'s library code must not
        # import world/ (AGENTS.md). A management command is an entry
        # point, the same way schedule/'s load_season and teams/'s own
        # seed_teams read the clock themselves.
        from world.services import now

        spell = release_team(team, reason=options["reason"], at=now())
        if spell is None:
            raise CommandError(f"{team} has no manager to release")

        self.stdout.write(
            f"released {spell.team_name} ({spell.team_code}) from "
            f"{spell.manager.email} — spell #{spell.pk}"
        )
