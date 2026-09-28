from __future__ import annotations

from django.db import models

from core.models import TimeStampedModel

#: The balance every team starts on, and that a claim resets to. Game
#: balance, not deployment configuration — deliberately here, not in
#: settings. A twelve-rider team burns WEEKLY_WAGE_PER_RIDER * 12 = 14,400
#: a week, so this covers roughly 34 weeks — down to roughly 26 once the
#: team also carries a top-end trainer on SALARY_AT_MAX_SPECIALITY = 4,500
#: a week. Still comfortably past a season, and not worth retuning before
#: prize money (#19) and sponsorship (#22) land.
STARTING_BALANCE = 500_000
#: What a rider costs per week, on average. No longer charged directly —
#: #25 gave every rider their own weekly_salary (riders.pricing), each
#: calibrated so a generated population averages close to this figure.
#: Kept as the anchor that calibration is checked against
#: (riders/tests/test_pricing.py) and the figure STARTING_BALANCE's
#: comment above reasons from.
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
#: A sponsor's weekly baseline is fanbase // this, before the profile's own
#: multiplier (economy/sponsors.py). At STARTING_FANBASE (10,000) a BALANCED
#: offer (multiplier 1.0) pays 10,000 // 2 = 5,000/week — the largest single
#: income stream against the 14,400/week wage bill (~35%, spec: "largest
#: income stream") and nowhere near covering it alone. Tunable.
SPONSOR_FANBASE_PER_CREDIT = 2
#: Offers generated per round. Always one of each SponsorProfile (economy/
#: sponsors.py) so the player sees the full spread of the decision.
OFFERS_PER_ROUND = 3


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
        SPONSORSHIP = "sponsorship", "Sponsorship"
        TRAINER_SALARY = "trainer_salary", "Trainer salary"
        TRAINER_FEE = "trainer_fee", "Trainer hire fee"
        TRANSFER_FEE = "transfer_fee", "Transfer fee"
        # Two kinds, not one: the weekly cost recurs and so needs the
        # (team, week) unique constraint that keeps a re-tick from charging
        # twice, while the one-off opening or upgrade fee does not and must
        # not be swept up by it. "development_squad" is the weekly one, and
        # its 17 characters and the 21-character fee name are why `kind` is
        # max_length=32 below (Design decision 10).
        DEVELOPMENT_SQUAD = "development_squad", "Development squad"
        DEVELOPMENT_SQUAD_FEE = "development_squad_fee", "Development squad fee"

    team = models.ForeignKey(
        "teams.Team",
        on_delete=models.CASCADE,
        related_name="ledger_entries",
        help_text="Deleting a team deletes its financial history; it has no meaning without the team.",
    )
    # max_length=32, not 20: `development_squad_fee` is 21 characters, so
    # the old limit was one short of the names now in use. It was never a real
    # constraint — every earlier value fitted well inside it — just a round
    # number that had not yet met a name that did not. Widened in
    # economy/migrations/0011_development_squad_kinds.py along with the kinds
    # that need it (Design decision 10).
    kind = models.CharField(max_length=32, choices=Kind.choices)
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
        help_text="Set on wages, sponsorship and trainer salary entries only. Null elsewhere.",
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
            models.UniqueConstraint(
                fields=["team", "week"],
                condition=models.Q(kind="sponsorship"),
                name="one_sponsorship_entry_per_team_per_week",
            ),
            models.UniqueConstraint(
                fields=["team", "week"],
                condition=models.Q(kind="trainer_salary"),
                name="one_trainer_salary_per_team_per_week",
            ),
            # The weekly squad cost's exactly-once rule, and the only reason
            # DEVELOPMENT_SQUAD is its own kind rather than sharing
            # TRAINER_SALARY's. It does one job: re-running a tick writes
            # nothing, so a crash or a second call cannot double-charge a
            # week. It is not what makes "opened mid-week pays at the next
            # boundary" true — that falls out of the tick only processing the
            # boundaries since the last one, the same as wages (Design
            # decision 7). The one-off fee deliberately has no such
            # constraint: a team may open, upgrade and reopen across a season,
            # and each of those is its own row.
            models.UniqueConstraint(
                fields=["team", "week"],
                condition=models.Q(kind="development_squad"),
                name="one_development_squad_cost_per_team_per_week",
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


_SPONSOR_PROFILE_CHOICES = [("steady", "Steady"), ("balanced", "Performance-driven"), ("demanding", "Results-hungry")]


class SponsorOffer(TimeStampedModel):
    """One unsigned sponsor offer, part of a team's round for a season.

    Disposable: a round is regenerated wholesale (economy/README.md,
    *Sponsorship*), which means deleting a team's unsigned offers. Kept as
    a separate table from SponsorContract precisely so that delete can never
    touch signed, permanent history — see economy/README.md, D1.
    """

    team = models.ForeignKey(
        "teams.Team",
        on_delete=models.CASCADE,
        related_name="sponsor_offers",
        help_text="Deleting a team deletes its unsigned offers; they have no meaning without it.",
    )
    season = models.ForeignKey(
        "schedule.Season",
        on_delete=models.CASCADE,
        related_name="sponsor_offers",
        help_text="The season this round of offers was generated for.",
    )
    profile = models.CharField(max_length=20, choices=_SPONSOR_PROFILE_CHOICES)
    sponsor_name = models.CharField(max_length=80, help_text="Flavour, rolled at generation.")
    weekly_base = models.PositiveIntegerField(help_text="Credits/week before results-based swing.")
    floor_amount = models.PositiveIntegerField(help_text="The low end of the range shown at signing.")
    ceiling_amount = models.PositiveIntegerField(help_text="The high end of the range shown at signing.")
    sensitivity = models.FloatField(help_text="Copied from the profile at generation.")

    class Meta:
        ordering = ["pk"]
        constraints = [
            models.UniqueConstraint(
                fields=["team", "season", "profile"],
                name="one_offer_per_profile_per_team_per_season",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.team} — {self.sponsor_name} offer ({self.profile})"


class SponsorContract(TimeStampedModel):
    """One signed sponsorship contract, permanent financial history.

    Terms are COPIED from the offer at signing, never read through `offer`
    at payment time (economy/README.md, D2) — `offer` survives only as
    provenance and is SET_NULL because the rest of that round's offers are
    deleted once one is signed. A voided contract (claimed away from its
    manager) is never deleted, only marked — see economy/README.md, D7.
    """

    team = models.ForeignKey(
        "teams.Team",
        on_delete=models.CASCADE,
        related_name="sponsor_contracts",
        help_text="Deleting a team deletes its sponsorship history; it has no meaning without it.",
    )
    season = models.ForeignKey(
        "schedule.Season",
        on_delete=models.PROTECT,
        related_name="sponsor_contracts",
        help_text="A season with contracts is financial history; it may not be deleted out from under them.",
    )
    offer = models.ForeignKey(
        SponsorOffer,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="contract",
        help_text="Provenance only. Terms are copied onto this row and never re-read from here.",
    )
    profile = models.CharField(max_length=20, choices=_SPONSOR_PROFILE_CHOICES)
    sponsor_name = models.CharField(max_length=80)
    weekly_base = models.PositiveIntegerField()
    floor_amount = models.PositiveIntegerField()
    ceiling_amount = models.PositiveIntegerField()
    sensitivity = models.FloatField()
    signed_at = models.DateTimeField(help_text="Game time, from the caller.")
    voided_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Set when the team is claimed by someone else. Non-null means it never pays again.",
    )

    class Meta:
        ordering = ["-signed_at", "-pk"]
        constraints = [
            models.UniqueConstraint(
                fields=["team", "season"],
                condition=models.Q(voided_at__isnull=True),
                name="one_active_contract_per_team_per_season",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.team} — {self.sponsor_name} contract ({self.profile})"


class SalaryReviewReport(TimeStampedModel):
    """What a season close's re-pricing did for one team's wage bill.

    A convenience snapshot for the Roster screen, written the moment the
    re-pricing happens — the stored salary afterwards cannot tell you what
    it was before. Living in economy/ because it is a statement about a
    team's wage bill (economy/README.md, *Salary review*); `season` is a
    string reference so economy/models.py needs no import of schedule/
    (AGENTS.md), the same pattern SponsorOffer/SponsorContract use.
    """

    team = models.ForeignKey(
        "teams.Team",
        on_delete=models.CASCADE,
        related_name="salary_reviews",
        help_text="A deleted team's reviews go with it.",
    )
    season = models.ForeignKey(
        "schedule.Season",
        on_delete=models.CASCADE,
        related_name="salary_reviews",
        help_text="The season that just closed.",
    )
    changes = models.JSONField(
        default=list,
        help_text=(
            '[{"rider_id", "rider_name", "from", "to"}], whole credits. Only '
            "riders whose wage moved by at least the report threshold. An "
            "empty list is normal and valid."
        ),
    )
    payroll_before = models.PositiveIntegerField(
        help_text="Team's total weekly wage bill before re-pricing.",
    )
    payroll_after = models.PositiveIntegerField(
        help_text="Team's total weekly wage bill after re-pricing.",
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["team", "season"], name="one_salary_review_per_team_per_season",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.team}, {self.season}"