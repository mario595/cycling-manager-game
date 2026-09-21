from __future__ import annotations

from django.db import models

from core.models import TimeStampedModel

#: The balance every team starts on, and that a claim resets to. Game
#: balance, not deployment configuration — deliberately here, not in
#: settings. A twelve-rider team burns WEEKLY_WAGE_PER_RIDER * 12 = 14,400
#: a week, so this covers roughly 34 weeks — comfortably past a season.
STARTING_BALANCE = 500_000
#: The flat wage one rider costs per week. What #25 replaces with a
#: per-rider salary.
WEEKLY_WAGE_PER_RIDER = 1_200
#: The fanbase every team starts on, and that a claim resets to. Game
#: balance, not deployment configuration — deliberately here, not in
#: settings. A twelve-rider team costs WEEKLY_WAGE_PER_RIDER * 12 = 14,400
#: a week; at STARTING_FANBASE merchandise pays 400, ~2.8% of that — visible,
#: nowhere near solvency (spec, *Rules and edge cases*). Tunable; do not
#: retune to balance the economy now, before prize money (#19) and
#: sponsorship (#22).
STARTING_FANBASE = 10_000
#: Fanbase never falls below this. Applied at write time by clamping the
#: delta, so the sum of rows is never below the floor.
MINIMUM_FANBASE = 1_000
#: A flat weekly loss every team pays, winners included. A scoring week is
#: a gain that outweighs the same decay, not decay skipped.
WEEKLY_FANBASE_DECAY = 150
#: Fanbase gained per race point scored in a week.
FANBASE_PER_POINT = 40
#: How many fans earn one merchandise credit: fanbase // 25. Integer divisor
#: keeps credits whole (the ledger is BigIntegerField, never Decimal).
MERCHANDISE_FANBASE_PER_CREDIT = 25


class LedgerEntry(TimeStampedModel):
    """One row of a team's append-only financial history.

    A team's balance is the sum of these rows — there is deliberately no
    balance column anywhere (`economy/README.md`, *The ledger is
    append-only*). `amount` is a signed integer: income positive,
    spending negative. `occurred_at` is game time — for wages, the week's
    own start, not the moment the tick happened to notice; `created_at`/
    `updated_at` (from `TimeStampedModel`) are the real time the row was
    written.
    """

    class Kind(models.TextChoices):
        STARTING_BALANCE = "starting_balance", "Starting balance"
        WAGES = "wages", "Weekly wages"
        TAKEOVER = "takeover", "Team taken over"
        PRIZE_MONEY = "prize_money", "Prize money"
        MERCHANDISE = "merchandise", "Merchandise revenue"

    team = models.ForeignKey(
        "teams.Team",
        on_delete=models.CASCADE,
        related_name="ledger_entries",
        help_text="Deleting a team deletes its financial history; it has no meaning without the team.",
    )
    kind = models.CharField(max_length=20, choices=Kind.choices)
    amount = models.BigIntegerField(
        help_text="Signed credits. Negative is expenditure. Never Positive*, never Decimal — see economy/README.md.",
    )
    occurred_at = models.DateTimeField(
        help_text="Game time. For wages, the week's own starts_at — not the moment the tick noticed.",
    )
    week = models.ForeignKey(
        "schedule.Week",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="ledger_entries",
        help_text="Set on wages entries only. Null elsewhere.",
    )
    race = models.ForeignKey(
        "racing.Race",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="ledger_entries",
        help_text=(
            "Set on prize_money entries only. Null elsewhere. Declared as a "
            "string so economy/ never imports racing/ at module scope — same "
            "pattern as staff.TrainingWeekReport.week."
        ),
    )
    position = models.PositiveSmallIntegerField(
        null=True,
        blank=True,
        help_text="The finishing position this prize was for, 1-10. Meaningful only on prize_money; null elsewhere.",
    )
    rider_count = models.PositiveSmallIntegerField(
        default=0,
        help_text="How many riders this charge covered. Meaningful only on wages; 0 elsewhere.",
    )
    description = models.CharField(
        max_length=120,
        help_text="Player-facing label, e.g. \"Weekly wages\". Written at creation; never recomputed.",
    )

    class Meta:
        ordering = ["-occurred_at", "-pk"]
        constraints = [
            models.UniqueConstraint(
                fields=["team", "week"],
                condition=models.Q(kind="wages"),
                name="one_wage_entry_per_team_per_week",
            ),
            models.UniqueConstraint(
                fields=["team", "race", "position"],
                condition=models.Q(kind="prize_money"),
                name="one_prize_entry_per_team_race_position",
            ),
            models.UniqueConstraint(
                fields=["team", "week"],
                condition=models.Q(kind="merchandise"),
                name="one_merchandise_entry_per_team_per_week",
            ),
        ]
        indexes = [
            models.Index(fields=["team", "-occurred_at"], name="ledger_team_recent_idx"),
            models.Index(fields=["race"], name="ledger_race_idx"),
        ]

    def __str__(self) -> str:
        return f"{self.team} — {self.description} ({self.amount})"


class FanbaseEntry(TimeStampedModel):
    """One row of a team's append-only fanbase history.

    A team's fanbase is the sum of these rows — there is deliberately no
    fanbase column anywhere (`economy/README.md`, *Fanbase is derived too*).
    `delta` is a signed integer: growth positive, decay negative, already
    floor-clamped at write time so the sum never falls below MINIMUM_FANBASE.
    `occurred_at` is game time — for weekly rows, the week's own start, not
    the moment the tick happened to notice; `created_at`/`updated_at` (from
    `TimeStampedModel`) are the real time the row was written.
    """

    class Kind(models.TextChoices):
        STARTING = "starting", "Starting fanbase"
        WEEKLY = "weekly", "Weekly change"
        TAKEOVER = "takeover", "Team taken over"

    team = models.ForeignKey(
        "teams.Team",
        on_delete=models.CASCADE,
        related_name="fanbase_entries",
        help_text="Deleting a team deletes its fanbase history; it has no meaning without the team.",
    )
    kind = models.CharField(max_length=20, choices=Kind.choices)
    delta = models.IntegerField(
        help_text="Signed fans gained (+) or lost (-). Already floor-clamped at write time.",
    )
    occurred_at = models.DateTimeField(
        help_text="Game time. For weekly rows, the week's own starts_at — not the moment the tick noticed.",
    )
    week = models.ForeignKey(
        "schedule.Week",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="fanbase_entries",
        help_text="Set on weekly rows only. Null elsewhere.",
    )
    points = models.PositiveSmallIntegerField(
        default=0,
        help_text="Race points that drove this row. Meaningful on weekly only.",
    )
    description = models.CharField(
        max_length=120,
        help_text="Player-facing label, e.g. \"Weekly fanbase change\". Written at creation; never recomputed.",
    )

    class Meta:
        ordering = ["-occurred_at", "-pk"]
        constraints = [
            models.UniqueConstraint(
                fields=["team", "week"],
                condition=models.Q(kind="weekly"),
                name="one_fanbase_entry_per_team_per_week",
            ),
        ]
        indexes = [
            models.Index(fields=["team", "-occurred_at"], name="fanbase_team_recent_idx"),
        ]

    def __str__(self) -> str:
        return f"{self.team} — {self.description} ({self.delta})"