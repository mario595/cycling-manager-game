from __future__ import annotations

from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q

from core.models import TimeStampedModel

#: A squad is exactly this many riders — see racing/README.md, *Squads*.
#: Imported by services, serializers and tests so the number appears once.
SQUAD_SIZE = 4


class StageRace(TimeStampedModel):
    """A named run of consecutive-day races sharing one squad and a general
    classification (see racing/README.md, *Stage races*, and
    specs/archive/stage-races.md).

    Deliberately stores nothing derivable from its stages: no status, no
    stage count, no GC. `is_complete()` and `final_stage()` compute it from
    the `Race` rows in `stages` — the same "derived, not stored" principle
    `schedule/README.md` uses for the current season/week.
    """

    name = models.CharField(max_length=120)
    week = models.ForeignKey(
        "schedule.Week",
        on_delete=models.PROTECT,
        related_name="stage_races",
        help_text="String reference so racing/models.py needs no import of schedule/.",
    )

    def __str__(self) -> str:
        return self.name

    def final_stage(self) -> "Race":
        return self.stages.order_by("-stage_number").first()

    def is_complete(self) -> bool:
        """True once every stage has run — FINISHED or FAILED — and at
        least one actually finished. A stage race entirely FAILED never
        completes: there is nothing to settle a GC from."""
        stages = list(self.stages.all())
        if not stages:
            return False
        if any(s.status not in (Race.Status.FINISHED, Race.Status.FAILED) for s in stages):
            return False
        return any(s.status == Race.Status.FINISHED for s in stages)


class Race(TimeStampedModel):
    """A race that has been or will be simulated.

    The course lives here as JSON in the same shape the engine's config
    parser already accepts (a list of `{length, gradient}` segments), so a
    race can be built from an existing `race_engine/configs/*.json` without
    a translation step. `week` is the link to the season it belongs to
    (`schedule.Week`, see `racing/README.md`) — null means the race is not
    part of any season.

    `starts_at` and `finished_at` are **game** time, set and read by
    `world/`. `created_at`/`updated_at` (from `TimeStampedModel`) are real
    time — never confuse the two.
    """

    class Status(models.TextChoices):
        SCHEDULED = "scheduled", "Scheduled"
        RUNNING = "running", "Racing now"
        FINISHED = "finished", "Finished"
        FAILED = "failed", "Failed"

    name = models.CharField(max_length=150)
    course = models.JSONField(
        help_text="List of {length, gradient} segments, as the engine's config format.",
    )
    wind_enabled = models.BooleanField(default=True)
    wind_band = models.CharField(max_length=20, blank=True)

    seed = models.BigIntegerField(
        null=True,
        blank=True,
        help_text=(
            "Seed used for the simulation, stored for reproducibility. Note this "
            "does NOT make the log regenerable across engine versions — engine "
            "changes alter the outcome for the same seed, so the stored log is "
            "the only authoritative record of what happened."
        ),
    )

    starts_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Game time, on the hour. Null means unscheduled — never picked up by a tick.",
    )
    status = models.CharField(
        max_length=12, choices=Status.choices, default=Status.SCHEDULED,
    )
    finished_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Game time the result was recorded.",
    )
    week = models.ForeignKey(
        "schedule.Week",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="races",
        help_text="The season week this race belongs to. Null means not part of any season.",
    )
    race_day = models.DateField(
        null=True,
        blank=True,
        help_text=(
            "Derived from starts_at on save, never set directly. Exists only "
            "as the target of the one-race-per-day-per-week constraint — see "
            "racing/README.md."
        ),
    )
    stage_race = models.ForeignKey(
        StageRace,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="stages",
        help_text="Null for a one-day race. PROTECT: a raced stage must never vanish with its tour.",
    )
    stage_number = models.PositiveSmallIntegerField(
        null=True,
        blank=True,
        help_text="1-based. Null iff stage_race is null — see stage_number_iff_stage_race.",
    )

    class Meta:
        indexes = [
            models.Index(fields=["status", "starts_at"], name="race_due_idx"),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["week", "race_day"], name="one_race_per_day_per_week",
            ),
            models.UniqueConstraint(
                fields=["stage_race", "stage_number"], name="one_race_per_stage_number",
            ),
            models.CheckConstraint(
                condition=(
                    Q(stage_race__isnull=True, stage_number__isnull=True)
                    | Q(stage_race__isnull=False, stage_number__isnull=False, stage_number__gte=1)
                ),
                name="stage_number_iff_stage_race",
            ),
        ]

    def __str__(self) -> str:
        return self.name

    def clean(self):
        super().clean()
        if self.week_id and self.starts_at:
            if not (self.week.starts_at <= self.starts_at < self.week.ends_at):
                raise ValidationError({
                    "starts_at": f"must fall inside week {self.week.number} of season "
                                 f"{self.week.season.number} "
                                 f"({self.week.starts_at} to {self.week.ends_at})",
                })
        if self.stage_race_id and self.week_id and self.stage_race.week_id != self.week_id:
            raise ValidationError({
                "week": f"must be the same week as its stage race ({self.stage_race})",
            })

    def save(self, *args, **kwargs):
        self.clean()
        self.race_day = self.starts_at.date() if self.starts_at else None
        super().save(*args, **kwargs)


class RaceLog(TimeStampedModel):
    """Pointer to a simulated race's tick-by-tick log file.

    The log itself is **never** stored in the database — it is large (megabytes
    per race, growing with distance x riders) and is only ever read as a whole
    by the race player. It is written through Django's storage API so that
    moving it to object storage later is a settings change.

    The log is a single brotli-compressed JSONL file: one header line, then a
    sampled tick-by-tick payload. ``sample_count`` tells a caller how many
    samples the header plus ``tick_interval`` would predict, and ``size_bytes``
    is the compressed file's size — the pair is interpretable without opening
    the file. Storage, sampling and compression within the file are `race_engine`'s
    job; this row just points at the stored result.
    """

    race = models.OneToOneField(Race, on_delete=models.CASCADE, related_name="log")
    file = models.FileField(upload_to="race_logs/")
    sample_count = models.PositiveIntegerField(default=0)
    tick_interval = models.PositiveSmallIntegerField(default=2)
    size_bytes = models.PositiveBigIntegerField(
        default=0,
        help_text="Size of the compressed log file on disk.",
    )

    def __str__(self) -> str:
        return f"log for {self.race}"


class RaceResult(TimeStampedModel):
    """One rider's finishing position in one race.

    Kept in the database (unlike the log) because standings, prize money and
    rider history all query it, and it stays small — one row per rider per
    race.
    """

    race = models.ForeignKey(Race, on_delete=models.CASCADE, related_name="results")
    rider = models.ForeignKey(
        "riders.Rider", on_delete=models.CASCADE, related_name="results"
    )
    position = models.PositiveSmallIntegerField()
    finish_time = models.FloatField(
        null=True,
        blank=True,
        help_text="Seconds from race start. Null if the rider did not finish.",
    )
    group_time = models.FloatField(
        null=True,
        blank=True,
        help_text=(
            "This rider's finishing group's time — the earliest finish_time "
            "among riders separated by no more than GROUP_GAP_SECONDS from "
            "the rider ahead. Null for a non-finisher. Written for every "
            "race, but only read for a stage race's general classification "
            "— see racing/README.md, *Stage races*."
        ),
    )

    class Meta:
        ordering = ["race", "position"]
        constraints = [
            models.UniqueConstraint(
                fields=["race", "rider"], name="unique_result_per_rider_per_race"
            ),
            models.UniqueConstraint(
                fields=["race", "position"], name="unique_position_per_race"
            ),
        ]

    def __str__(self) -> str:
        return f"{self.position}. {self.rider} in {self.race}"


class RaceSquad(TimeStampedModel):
    """One team's entry into one race: which riders, and who leads them.

    The four/one-leader rule is enforced by `racing.services.set_squad`
    (the only sanctioned writer), not by a database constraint — Postgres
    cannot express "this parent has exactly four children" without a
    trigger. See `racing/README.md`, *Squads*.
    """

    race = models.ForeignKey(Race, on_delete=models.CASCADE, related_name="squads")
    team = models.ForeignKey(
        "teams.Team",
        on_delete=models.CASCADE,
        related_name="race_squads",
        help_text="String reference so racing/models.py needs no import of teams/.",
    )
    is_auto_picked = models.BooleanField(
        default=False,
        help_text="True when written by ensure_squads/auto_pick_squad, false when a manager saved it.",
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["race", "team"], name="one_squad_per_team_per_race"),
        ]
        indexes = [
            models.Index(fields=["team", "race"], name="squad_team_race_idx"),
        ]

    def __str__(self) -> str:
        return f"{self.team}'s squad for {self.race}"


class RaceSquadRider(models.Model):
    """One rider's membership in a squad.

    Not a `TimeStampedModel`: these rows are written and deleted as a set by
    `set_squad`, never individually amended, so per-row audit columns are
    noise — the same reasoning `schedule.Week` records.
    """

    squad = models.ForeignKey(RaceSquad, on_delete=models.CASCADE, related_name="members")
    rider = models.ForeignKey(
        "riders.Rider",
        on_delete=models.CASCADE,
        related_name="squad_entries",
        help_text="String reference so racing/models.py needs no import of riders/.",
    )
    is_leader = models.BooleanField(
        default=False,
        help_text="Exactly one per squad — enforced in set_squad, not by the database.",
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["squad", "rider"], name="unique_rider_per_squad"),
        ]

    def __str__(self) -> str:
        return f"{self.rider} in {self.squad}"


class RaceMarker(models.Model):
    """A point on a race's course that riders race over (see specs/course-markers).

    Written as a set with its race and never amended, so not a
    `TimeStampedModel` — the same reasoning `RaceSquadRider` records.

    Marker index `i` in the engine means the same row here: `simulate_race`
    fetches the markers once, ordered by `("distance", "pk")`, and passes
    that same list to both the adapter and the crossing writer (D9).
    """

    class Kind(models.TextChoices):
        SPRINT = "sprint", "Sprint"
        MOUNTAIN = "mountain", "Mountain"

    race = models.ForeignKey(Race, on_delete=models.CASCADE, related_name="markers")
    kind = models.CharField(max_length=10, choices=Kind.choices)
    name = models.CharField(max_length=100)
    distance = models.FloatField(
        help_text="Meters from the start, same unit as Race.course lengths.",
    )

    class Meta:
        ordering = ["distance", "pk"]

    def __str__(self) -> str:
        return f"{self.name} ({self.kind}) at {self.distance:.0f} m in {self.race}"

    def clean(self):
        super().clean()
        errors = {}
        if not self.name.strip():
            errors["name"] = "must not be blank."
        course_length = sum(s["length"] for s in self.race.course)
        if not (0 < self.distance <= course_length):
            errors["distance"] = (
                f"must be within 0 and {course_length:.0f} m of the course."
            )
        if errors:
            raise ValidationError(errors)

    def save(self, *args, **kwargs):
        self.clean()
        super().save(*args, **kwargs)


class MarkerCrossing(models.Model):
    """One rider crossing one race marker.

    Rows are written as a set by `simulate_race` and never amended — not a
    `TimeStampedModel`. `crossed_at` is race seconds; for a marker not on the
    finish line it is interpolated inside the engine tick (D4), and for a
    finish-line marker it is the rider's `finish_time` (D5).
    """

    marker = models.ForeignKey(RaceMarker, on_delete=models.CASCADE, related_name="crossings")
    rider = models.ForeignKey(
        "riders.Rider",
        on_delete=models.CASCADE,
        related_name="marker_crossings",
        help_text="String reference so racing/models.py needs no import of riders/.",
    )
    position = models.PositiveSmallIntegerField(
        help_text="1 = first across. Contiguous from 1 within the marker.",
    )
    crossed_at = models.FloatField(help_text="Race seconds from the race start.")

    class Meta:
        ordering = ["marker", "position"]
        constraints = [
            models.UniqueConstraint(
                fields=["marker", "rider"], name="unique_crossing_per_rider_per_marker"
            ),
            models.UniqueConstraint(
                fields=["marker", "position"], name="unique_position_per_marker"
            ),
        ]

    def __str__(self) -> str:
        return f"{self.position}. {self.rider} over {self.marker.name}"
