from __future__ import annotations

import json
from collections import Counter

from django.core.management.base import BaseCommand, CommandError

from racing.calendar_check import (
    WINNING_SPECIALITIES,
    check_calendar,
    general_classification,
    judge,
)
from schedule.loaders import SeasonFileError, parse_season_file


class Command(BaseCommand):
    help = (
        "Simulate every race day of a season file against freshly generated "
        "fields, one per seed, and report which speciality wins each — the "
        "calendar balance check (specs/beta-world.md). Writes nothing to the "
        "database. Exits non-zero when a winning speciality wins fewer than "
        "two race days a season, or any speciality more than 40% of them."
    )

    def add_arguments(self, parser):
        parser.add_argument("path", help="Path to the season JSON file.")
        parser.add_argument(
            "--seeds", default="1,2,3",
            help="Comma-separated field seeds, one simulated season each (default 1,2,3).",
        )
        parser.add_argument("--jobs", type=int, default=1, help="Worker processes (default 1).")
        parser.add_argument(
            "--only", default=None,
            help="Only run race days whose name contains this text — for tuning one course.",
        )

    def handle(self, *args, **options):
        try:
            with open(options["path"]) as f:
                declaration = parse_season_file(json.load(f))
        except (OSError, json.JSONDecodeError, SeasonFileError) as exc:
            raise CommandError(str(exc))

        if options["only"]:
            needle = options["only"].lower()
            declaration.races[:] = [r for r in declaration.races if needle in r.name.lower()]
            for tour in list(declaration.stage_races):
                if needle not in tour.name.lower():
                    declaration.stage_races.remove(tour)

        seeds = [int(s) for s in options["seeds"].split(",") if s.strip()]

        def show(result):
            self.stdout.write(
                f"seed {result.field_seed:>3}  {result.day.label:<55} "
                f"{result.winner_speciality:<11} top3 {', '.join(result.top_three)}"
            )

        results = check_calendar(declaration, seeds, jobs=options["jobs"], on_result=show)

        self.stdout.write("")
        by_day: dict[str, Counter] = {}
        for r in results:
            by_day.setdefault(r.day.label, Counter())[r.winner_speciality] += 1
        for label, wins in by_day.items():
            summary = ", ".join(f"{s} {n}" for s, n in wins.most_common())
            self.stdout.write(f"  {label:<55} {summary}")

        for tour in declaration.stage_races:
            gcs = Counter(general_classification(results, tour.name, seed) for seed in seeds)
            summary = ", ".join(f"{s} {n}" for s, n in gcs.most_common())
            self.stdout.write(f"  {tour.name + ' (GC)':<55} {summary}")

        verdict = judge(results)
        self.stdout.write("")
        self.stdout.write(
            f"{verdict.days_per_seed} race days a season, {verdict.seeds} season(s) simulated"
        )
        for speciality, count in verdict.wins.most_common():
            per_season = count / verdict.seeds
            share = count / len(results)
            self.stdout.write(f"  {speciality:<11} {per_season:4.1f} a season  {share:4.0%}")
        for speciality in WINNING_SPECIALITIES:
            if speciality not in verdict.wins:
                self.stdout.write(f"  {speciality:<11}  0.0 a season    0%")

        if options["only"]:
            return
        if verdict.ok:
            self.stdout.write(self.style.SUCCESS("balanced"))
        else:
            for failure in verdict.failures:
                self.stdout.write(self.style.ERROR(failure))
            raise CommandError("calendar is not balanced")
