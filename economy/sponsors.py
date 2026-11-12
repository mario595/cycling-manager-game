"""Sponsor profiles and the pure money maths behind an offer and its weekly
payment.

No ORM, no Django — matching `riders/display.py` and `staff/generation.py`'s
split between pure calculation and the services that write it to the
database. See `economy/README.md`, *Sponsorship*.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class SponsorProfile:
    """One fixed sponsor character. A round always offers one of each — see
    PROFILES — so the player's three cards are never near-identical."""

    key: str
    label: str
    blurb: str
    base_multiplier: float
    sensitivity: float
    floor_fraction: float
    ceiling_fraction: float


#: The three profiles a round always offers, one each (spec, *Rules and edge
#: cases*: "the choice is never three near-identical cards"). STEADY has
#: sensitivity=0.0 and floor==ceiling==base, so it is genuinely flat with no
#: special case needed in payment_for.
PROFILES = (
    SponsorProfile(
        key="steady",
        label="Steady",
        blurb="Pays the same every week, whatever happens.",
        base_multiplier=0.85,
        sensitivity=0.0,
        floor_fraction=1.0,
        ceiling_fraction=1.0,
    ),
    SponsorProfile(
        key="balanced",
        label="Performance-driven",
        blurb="Pays more when you score, less when you don't.",
        base_multiplier=1.0,
        sensitivity=0.5,
        floor_fraction=0.6,
        ceiling_fraction=1.6,
    ),
    SponsorProfile(
        key="demanding",
        label="Results-hungry",
        blurb="Pays big for big results — and little for none.",
        base_multiplier=1.25,
        sensitivity=1.0,
        floor_fraction=0.35,
        ceiling_fraction=2.2,
    ),
)

PROFILES_BY_KEY = {profile.key: profile for profile in PROFILES}


def offer_terms(profile: SponsorProfile, fanbase: int, *, credits_per_thousand_fans: int) -> dict:
    """The four money figures for one offer at a given fanbase.

    floor_amount and ceiling_amount are derived from weekly_base ONCE, here,
    and then stored on the offer/contract (economy/README.md, D6) — payment
    never re-derives them, so a later constant change cannot silently
    reprice a contract already signed against a displayed promise.
    """
    weekly_base = round((fanbase * credits_per_thousand_fans // 1_000) * profile.base_multiplier)
    return {
        "weekly_base": weekly_base,
        "floor_amount": round(weekly_base * profile.floor_fraction),
        "ceiling_amount": round(weekly_base * profile.ceiling_fraction),
        "sensitivity": profile.sensitivity,
    }


def payment_for(
    *,
    weekly_base: int,
    floor_amount: int,
    ceiling_amount: int,
    sensitivity: float,
    points: int,
    average_points: float | None,
) -> int:
    """This week's sponsorship payment, clamped into [floor_amount,
    ceiling_amount].

    `average_points` is the team's own season-to-date mean points per
    settled week (economy/README.md, D3) — None means no history yet (week
    1, or a freshly claimed team), which pays weekly_base exactly, same as
    a zero-sensitivity (STEADY) contract.

    The ratio is computed against a floor of 1.0 on the average, so a team
    averaging zero does not divide by zero — scoring anything at all then
    reads as beating that average.

    The clamp applies to the final AMOUNT, never to the ratio: the range
    shown at signing is a promise about credits, and clamping the ratio
    first would let rounding push the result outside it.
    """
    if average_points is None or sensitivity == 0.0:
        amount = weekly_base
    else:
        baseline = max(average_points, 1.0)
        ratio = points / baseline
        amount = round(weekly_base * (1.0 + sensitivity * (ratio - 1.0)))
    return max(floor_amount, min(ceiling_amount, amount))
