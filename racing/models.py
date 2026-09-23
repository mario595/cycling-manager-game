from __future__ import annotations

from django.core.exceptions import ValidationError
from django.db import models

from core.models import TimeStampedModel

#: A squad is exactly this many riders — see racing/README.md, *Squads*.
#: Imported by services, serializers and tests so the number appears once.
SQUAD_SIZE = 4


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

    class Meta:
        indexes = [
            models.Index(fields=["status", "starts_at"], name="race_due_idx"),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["week", "race_day"], name="one_race_per_day_per_week",
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
