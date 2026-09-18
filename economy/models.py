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
        ]
        indexes = [
            models.Index(fields=["team", "-occurred_at"], name="ledger_team_recent_idx"),
        ]

    def __str__(self) -> str:
        return f"{self.team} — {self.description} ({self.amount})"