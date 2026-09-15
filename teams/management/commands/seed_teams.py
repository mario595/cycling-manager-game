from __future__ import annotations

from django.core.management.base import BaseCommand
from django.db import transaction

from riders.generation import generate_roster
from riders.models import Rider
from teams.models import Team

DEFAULT_TEAM_COUNT = 16
DEFAULT_RIDERS_PER_TEAM = 12

#: Plausible team names paired with a derived three-letter code. Seed data,
#: not game logic — kept here rather than in teams/models.py or a fixture.
#: If --count exceeds this list, names are suffixed numerically (name N,
#: code with its last character replaced by the digit).
TEAM_NAMES: list[tuple[str, str]] = [
    ("Ardennes Racing", "ARD"),
    ("Pyrenees Cycling", "PYR"),
    ("Alpine Velo", "ALP"),
    ("Dolomiti Corsa", "DOL"),
    ("Flanders Elite", "FLA"),
    ("Vosges Rouleurs", "VOS"),
    ("Sierra Nevada", "SIE"),
    ("Carpathian Cycling", "CAR"),
    ("Basque Coast", "BAS"),
    ("Tuscan Hills", "TUS"),
    ("Cantabrian Racing", "CAN"),
    ("Provence Velo", "PRO"),
    ("Black Forest", "BLF"),
    ("Massif Central", "MAS"),
    ("Andalusian Sprint", "AND"),
    ("Apennine Corsa", "APE"),
]

#: A small palette so seeded teams are visually distinct in the race player
#: rather than all sharing Team.primary_colour's default. Paired
#: (primary, secondary); cycled if --count exceeds the palette.
COLOUR_PALETTE: list[tuple[str, str]] = [
    ("#1E88E5", "#FFFFFF"),
    ("#D32F2F", "#FFFFFF"),
    ("#388E3C", "#FFFFFF"),
    ("#F9A825", "#212121"),
    ("#6A1B9A", "#FFFFFF"),
    ("#00838F", "#FFFFFF"),
    ("#E64A19", "#FFFFFF"),
    ("#5D4037", "#FFFFFF"),
]


#: Letters cycled onto a code's last character for the second, third, ...
#: pass through TEAM_NAMES, so a suffixed code still satisfies
#: team_code_validator (exactly three uppercase letters — no digits).
_GENERATION_LETTERS = "XYZWVUTSRQPONM"


def _name_and_code(index: int) -> tuple[str, str]:
    """The name and code for the `index`-th seeded team (0-based).

    Cycles through TEAM_NAMES, suffixing with a generation number once the
    list is exhausted so names stay distinguishable — "Ardennes Racing 2" —
    and replacing the code's last letter with one of _GENERATION_LETTERS so
    the code stays three uppercase letters, e.g. "ARX"."""
    base_name, base_code = TEAM_NAMES[index % len(TEAM_NAMES)]
    generation = index // len(TEAM_NAMES)
    if generation == 0:
        return base_name, base_code
    letter = _GENERATION_LETTERS[(generation - 1) % len(_GENERATION_LETTERS)]
    return f"{base_name} {generation + 1}", f"{base_code[:2]}{letter}"


class Command(BaseCommand):
    help = (
        "Create unmanaged teams, each with a freshly generated roster, so "
        "there is something for a registered player to claim — see "
        "teams/README.md and specs/claiming-a-team.md. Adds teams by "
        "default; --reset deletes every unmanaged team (and their riders) "
        "first. Never touches a managed team."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--count", type=int, default=DEFAULT_TEAM_COUNT,
            help=f"Unmanaged teams to create (default {DEFAULT_TEAM_COUNT}).",
        )
        parser.add_argument(
            "--per-team", type=int, default=DEFAULT_RIDERS_PER_TEAM,
            help=f"Riders generated per team (default {DEFAULT_RIDERS_PER_TEAM}).",
        )
        parser.add_argument(
            "--reset", action="store_true",
            help="Delete every unmanaged team and its riders first. A managed "
            "team, and its riders, are never touched, reset or not.",
        )

    def handle(self, *args, **options):
        count = options["count"]
        per_team = options["per_team"]

        with transaction.atomic():
            if options["reset"]:
                # Imported here, not at module scope: teams/'s library code
                # must never import racing/ (AGENTS.md). This management
                # command is an entry point, like riders/'s reset_riders —
                # see teams/README.md.
                from racing.models import RaceResult, RaceSquad

                unmanaged = Team.objects.filter(manager__isnull=True)
                riders_to_drop = Rider.objects.filter(team__in=unmanaged)
                result_count = RaceResult.objects.filter(rider__in=riders_to_drop).count()
                RaceResult.objects.filter(rider__in=riders_to_drop).delete()
                squad_count = RaceSquad.objects.filter(team__in=unmanaged).count()
                RaceSquad.objects.filter(team__in=unmanaged).delete()
                rider_count = riders_to_drop.count()
                riders_to_drop.delete()
                team_count = unmanaged.count()
                unmanaged.delete()
                self.stdout.write(
                    f"deleted {team_count} unmanaged team(s), {rider_count} "
                    f"rider(s), {result_count} result(s), {squad_count} squad(s)"
                )

            created_teams = 0
            created_riders = 0
            for index in range(count):
                name, code = _name_and_code(index)
                primary, secondary = COLOUR_PALETTE[index % len(COLOUR_PALETTE)]
                team = Team.objects.create(
                    name=name, code=code,
                    primary_colour=primary, secondary_colour=secondary,
                )
                roster = generate_roster(per_team, team=team)
                Rider.objects.bulk_create(roster)
                created_teams += 1
                created_riders += len(roster)

        self.stdout.write(
            f"created {created_teams} unmanaged team(s), "
            f"{created_riders} rider(s)"
        )
