"""Simulating a race and recording its result.

`racing/` owns simulation; `world/` calls it — never the reverse (`AGENTS.md`
forbids `racing/` importing `world/`). `game_time` is therefore a parameter,
not read from the clock here.
"""

from __future__ import annotations

import tempfile
from datetime import datetime
from pathlib import Path

from django.core.files.base import ContentFile
from django.db import transaction

from riders.models import Rider

from .adapters import run_race_via_adapter, to_engine_course, to_engine_rider, to_team_codes
from .models import Race, RaceLog, RaceResult


def simulate_race(race: Race, *, game_time: datetime) -> list[RaceResult]:
    """Run one race through the engine and record it.

    `game_time` is the world's current game time, passed in because
    `racing/` may not import `world/`. It is stored as `Race.finished_at`.

    Assumes the caller has already claimed the race (status RUNNING). Writes
    the log through Django storage, the results in one transaction, and
    flips the race to FINISHED. Idempotent only in the sense that a FINISHED
    race is refused: call it once per claim.
    """
    if race.status == Race.Status.FINISHED:
        raise ValueError(f"{race} is already finished")

    db_riders = list(Rider.objects.select_related("team"))
    if not db_riders:
        raise ValueError("no riders to race")
    # Every rider in the database races: there is no squad selection yet
    # (#37) and no calendar to say who is entered. This is a deliberate
    # placeholder, not an oversight.
    teams = [r.team for r in db_riders if r.team_id]

    engine_riders = [to_engine_rider(r) for r in db_riders]
    course = to_engine_course(race)

    # The engine writes the log itself with a raw open(), and it may not
    # learn about Django. So it writes to a temp file and we hand the
    # finished file to storage — see racing/README.md, logs never bypass
    # the storage API.
    with tempfile.TemporaryDirectory() as tmp:
        log_path = Path(tmp) / f"race-{race.pk}.jsonl"
        states = run_race_via_adapter(
            engine_riders, course, str(log_path), race.seed,
            to_team_codes(teams), race.wind_enabled, race.wind_band or None,
        )
        tick_count = sum(1 for _ in log_path.open())
        size = log_path.stat().st_size
        with log_path.open("rb") as fh:
            saved = ContentFile(fh.read(), name=f"race-{race.pk}.jsonl")

    by_pk = {str(r.pk): r for r in db_riders}
    finishers = sorted(
        states,
        key=lambda s: (s.finish_time is None, s.finish_time if s.finish_time is not None else 0),
    )

    with transaction.atomic():
        RaceLog.objects.update_or_create(
            race=race,
            defaults={"file": saved, "tick_count": tick_count, "size_bytes": size},
        )
        results = RaceResult.objects.bulk_create([
            RaceResult(
                race=race, rider=by_pk[s.rider.id], position=i,
                finish_time=float(s.finish_time) if s.finish_time is not None else None,
            )
            for i, s in enumerate(finishers, start=1)
        ])
        race.status = Race.Status.FINISHED
        race.finished_at = game_time
        race.save(update_fields=["status", "finished_at"])
    return results
