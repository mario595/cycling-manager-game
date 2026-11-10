"""`transfers/`'s first models: an `Auction` needs a lifecycle (`open` ->
`sold` / `unsold` / `cancelled`) and a deadline that mutates as bids arrive
— a pure query, unlike the free-agent pool, can't represent that. `Bid` is
a normal append-only history row, the same shape `LedgerEntry` and
`FanbaseEntry` already use elsewhere.
"""

from __future__ import annotations

from django.db import models

from core.models import TimeStampedModel
from riders.models import Rider


class Auction(TimeStampedModel):
    """One rider listed for auction by its owning team.

    `reserve_price`, `current_price` and `min_increment` are frozen at
    listing time (and `current_price` updated at each bid) — never
    recomputed from `market_value_for` after creation, so a manager
    reasoning about a displayed price is never reasoning about a number
    that could move under them (Design decision 5).
    """

    class Status(models.TextChoices):
        OPEN = "open", "Open"
        SOLD = "sold", "Sold"
        UNSOLD = "unsold", "Unsold"
        CANCELLED = "cancelled", "Cancelled"

    rider = models.ForeignKey(
        Rider,
        on_delete=models.CASCADE,
        related_name="auctions",
        help_text="The rider being listed.",
    )
    seller_team = models.ForeignKey(
        "teams.Team",
        on_delete=models.CASCADE,
        related_name="listed_auctions",
        help_text="The team that owned the rider at listing time.",
    )
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.OPEN)
    reserve_price = models.PositiveIntegerField(
        help_text="Frozen at listing time; never recomputed from market value.",
    )
    current_price = models.PositiveIntegerField(
        help_text="reserve_price until the first bid, then the highest bid amount.",
    )
    min_increment = models.PositiveIntegerField(
        help_text="Frozen at listing time: reserve_price * MIN_INCREMENT_RATE.",
    )
    deadline = models.DateTimeField(
        help_text="Game time. Mutated forward by a qualifying late bid (Design decision 2).",
    )
    listed_at = models.DateTimeField(
        help_text="Game time the listing was made. Distinct from created_at (wall clock).",
    )
    resolved_at = models.DateTimeField(
        null=True, blank=True, help_text="Game time this auction left OPEN. Null while open.",
    )
    forced = models.BooleanField(
        default=False,
        help_text=(
            "A forced sale under insolvency (#27): the rider left the seller's "
            "roster at listing, and an unsold auction makes them a free agent."
        ),
    )

    class Meta:
        ordering = ["-listed_at", "-pk"]
        indexes = [
            models.Index(fields=["status", "deadline"], name="auction_open_deadline_idx"),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["rider"],
                condition=models.Q(status="open"),
                name="one_open_auction_per_rider",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.rider} — {self.get_status_display()} auction"


class BidQuerySet(models.QuerySet):
    def live(self):
        return self.filter(withdrawn_at__isnull=True)


class Bid(TimeStampedModel):
    """One bid against an auction. Append-only except for the one-way
    `withdrawn_at` stamp set when a team is claimed: the row remains as
    history, while live readers exclude the withdrawn intent."""

    auction = models.ForeignKey(Auction, on_delete=models.CASCADE, related_name="bids")
    bidder_team = models.ForeignKey(
        "teams.Team",
        on_delete=models.CASCADE,
        related_name="transfer_bids",
    )
    amount = models.PositiveIntegerField()
    placed_at = models.DateTimeField(help_text="Game time.")
    withdrawn_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Game time the bid was withdrawn when its team was claimed. Never cleared.",
    )

    objects = BidQuerySet.as_manager()

    class Meta:
        ordering = ["-placed_at", "-pk"]
        indexes = [models.Index(fields=["auction", "-amount"], name="bid_auction_amount_idx")]

    def __str__(self) -> str:
        return f"{self.bidder_team} bid {self.amount} on {self.auction_id}"
