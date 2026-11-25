from __future__ import annotations

import random
from datetime import datetime, timedelta, timezone as dt_timezone

import pytest

from economy.models import STARTING_FANBASE, FanbaseEntry, LedgerEntry, SponsorContract, SponsorOffer
from economy.services import (
    AlreadySponsored,
    OfferNotAvailable,
    active_contract,
    ensure_offer_round,
    ensure_starting_fanbase,
    offers_for,
    pay_sponsorship,
    sign_offer,
    sponsor_gap,
    void_sponsorship,
)
from schedule.models import Season, Week


@pytest.fixture
def season(db) -> Season:
    monday = datetime(2027, 3, 1, 0, 0, tzinfo=dt_timezone.utc)
    return Season.objects.create(number=1, starts_at=monday)


@pytest.fixture
def other_season(db) -> Season:
    return Season.objects.create(
        number=2, starts_at=datetime(2027, 6, 7, 0, 0, tzinfo=dt_timezone.utc),
    )


@pytest.fixture
def weeks(season) -> list[Week]:
    return [
        Week.objects.create(
            season=season, number=n,
            starts_at=season.starts_at + timedelta(weeks=n - 1),
            ends_at=season.starts_at + timedelta(weeks=n),
        )
        for n in range(1, 4)
    ]


# --- offer rounds -----------------------------------------------------

def test_round_is_one_offer_per_profile(db, team, season):
    offers = ensure_offer_round(team, season, at=season.starts_at)

    assert len(offers) == 3
    assert {o.profile for o in offers} == {"steady", "balanced", "demanding"}


def test_offer_round_at_starting_fanbase_pays_the_calibrated_baseline(db, team, season):
    # #125 sized sponsorship so the average team breaks even (economy/
    # README.md, *Balance targets*). Changing the rate must be a visible
    # edit here, not a silent drift.
    ensure_starting_fanbase(team, at=season.starts_at)
    assert STARTING_FANBASE == 10_000

    offers = ensure_offer_round(team, season, at=season.starts_at)

    bases = {o.profile: o.weekly_base for o in offers}
    assert bases == {"steady": 9_350, "balanced": 11_000, "demanding": 13_750}


def test_round_is_idempotent(db, team, season):
    first = ensure_offer_round(team, season, at=season.starts_at)
    second = ensure_offer_round(team, season, at=season.starts_at)

    assert len(first) == 3
    assert second == []
    assert SponsorOffer.objects.filter(team=team, season=season).count() == 3


def test_offers_scale_with_fanbase(db, team, other_team, season):
    ensure_starting_fanbase(team, at=season.starts_at)
    FanbaseEntry.objects.create(
        team=other_team, kind=FanbaseEntry.Kind.STARTING, delta=STARTING_FANBASE * 3,
        occurred_at=season.starts_at, description="Starting fanbase",
    )

    small = ensure_offer_round(team, season, at=season.starts_at, rng=random.Random(1))
    big = ensure_offer_round(other_team, season, at=season.starts_at, rng=random.Random(1))

    small_balanced = next(o for o in small if o.profile == "balanced")
    big_balanced = next(o for o in big if o.profile == "balanced")
    assert big_balanced.weekly_base > small_balanced.weekly_base


def test_round_does_not_regenerate_once_signed(db, team, season):
    offers = ensure_offer_round(team, season, at=season.starts_at)
    sign_offer(team, offers[0].pk, at=season.starts_at)

    again = ensure_offer_round(team, season, at=season.starts_at)

    assert again == []


# --- signing ------------------------------------------------------------

def test_signing_copies_terms_onto_the_contract(db, team, season):
    offers = ensure_offer_round(team, season, at=season.starts_at)
    chosen = offers[0]

    contract = sign_offer(team, chosen.pk, at=season.starts_at)

    assert contract.profile == chosen.profile
    assert contract.sponsor_name == chosen.sponsor_name
    assert contract.weekly_base == chosen.weekly_base
    assert contract.floor_amount == chosen.floor_amount
    assert contract.ceiling_amount == chosen.ceiling_amount
    assert contract.sensitivity == chosen.sensitivity


def test_signing_deletes_the_rest_of_the_round(db, team, season):
    offers = ensure_offer_round(team, season, at=season.starts_at)

    sign_offer(team, offers[0].pk, at=season.starts_at)

    # The signed offer is kept as the contract's provenance; its two
    # siblings are gone so the screen has nothing stale left to render.
    remaining = SponsorOffer.objects.filter(team=team, season=season)
    assert list(remaining.values_list("pk", flat=True)) == [offers[0].pk]


def test_contract_survives_after_its_offer_is_deleted(db, team, season):
    """The load-bearing case for D2: a contract's terms must not depend on
    the offer row that produced it, because that row can be deleted
    elsewhere (a later void_sponsorship, or a manual cleanup) without
    warning — SET_NULL, not CASCADE."""
    offers = ensure_offer_round(team, season, at=season.starts_at)
    chosen = offers[0]
    expected = (chosen.weekly_base, chosen.floor_amount, chosen.ceiling_amount)

    contract = sign_offer(team, chosen.pk, at=season.starts_at)
    SponsorOffer.objects.filter(pk=chosen.pk).delete()

    contract.refresh_from_db()
    assert contract.offer_id is None
    assert (contract.weekly_base, contract.floor_amount, contract.ceiling_amount) == expected


def test_second_sign_raises_already_sponsored(db, team, season):
    offers = ensure_offer_round(team, season, at=season.starts_at)
    sign_offer(team, offers[0].pk, at=season.starts_at)

    other_round = ensure_offer_round(team, season, at=season.starts_at)
    assert other_round == []  # already sponsored, no second round to sign from


def test_signing_another_teams_offer_is_refused(db, team, other_team, season):
    offers = ensure_offer_round(team, season, at=season.starts_at)

    with pytest.raises(OfferNotAvailable):
        sign_offer(other_team, offers[0].pk, at=season.starts_at)


def test_signing_a_missing_offer_is_refused(db, team, season):
    with pytest.raises(OfferNotAvailable):
        sign_offer(team, 999_999, at=season.starts_at)


# --- voiding --------------------------------------------------------------

def test_void_marks_contract_and_clears_offers(db, team, season):
    offers = ensure_offer_round(team, season, at=season.starts_at)
    contract = sign_offer(team, offers[0].pk, at=season.starts_at)

    void_sponsorship(team, at=season.starts_at + timedelta(weeks=2))

    contract.refresh_from_db()
    assert contract.voided_at is not None
    assert active_contract(team, season) is None


def test_void_clears_unsigned_offers_too(db, team, season):
    ensure_offer_round(team, season, at=season.starts_at)

    void_sponsorship(team, at=season.starts_at)

    assert offers_for(team, season).count() == 0


def test_void_of_nothing_is_a_safe_no_op(db, team, season):
    void_sponsorship(team, at=season.starts_at)  # no offers, no contract

    assert active_contract(team, season) is None


# --- weekly payment ---------------------------------------------------

def test_pays_one_entry_per_contracted_team(db, team, other_team, season, weeks):
    offers = ensure_offer_round(team, season, at=season.starts_at)
    sign_offer(team, offers[0].pk, at=season.starts_at)

    written = pay_sponsorship(weeks[0], points_by_team={})

    assert written == 1
    assert LedgerEntry.objects.filter(
        team=team, kind=LedgerEntry.Kind.SPONSORSHIP, week=weeks[0],
    ).count() == 1
    assert LedgerEntry.objects.filter(
        team=other_team, kind=LedgerEntry.Kind.SPONSORSHIP,
    ).count() == 0


def test_team_without_contract_gets_no_entry(db, team, season, weeks):
    written = pay_sponsorship(weeks[0], points_by_team={team.pk: 10})

    assert written == 0
    assert LedgerEntry.objects.filter(team=team, kind=LedgerEntry.Kind.SPONSORSHIP).count() == 0


def test_voided_contract_is_not_paid(db, team, season, weeks):
    offers = ensure_offer_round(team, season, at=season.starts_at)
    sign_offer(team, offers[0].pk, at=season.starts_at)
    void_sponsorship(team, at=season.starts_at)

    written = pay_sponsorship(weeks[0], points_by_team={team.pk: 10})

    assert written == 0


def test_entry_is_dated_to_the_week_start(db, team, season, weeks):
    offers = ensure_offer_round(team, season, at=season.starts_at)
    sign_offer(team, offers[0].pk, at=season.starts_at)

    pay_sponsorship(weeks[1], points_by_team={})

    entry = LedgerEntry.objects.get(team=team, kind=LedgerEntry.Kind.SPONSORSHIP, week=weeks[1])
    assert entry.occurred_at == weeks[1].starts_at


def test_second_call_for_the_same_week_writes_nothing(db, team, season, weeks):
    offers = ensure_offer_round(team, season, at=season.starts_at)
    sign_offer(team, offers[0].pk, at=season.starts_at)

    first = pay_sponsorship(weeks[0], points_by_team={team.pk: 5})
    second = pay_sponsorship(weeks[0], points_by_team={team.pk: 5})

    assert first == 1
    assert second == 0
    assert LedgerEntry.objects.filter(
        team=team, kind=LedgerEntry.Kind.SPONSORSHIP, week=weeks[0],
    ).count() == 1


def test_payment_stays_within_the_signed_range(db, team, season, weeks):
    offers = ensure_offer_round(team, season, at=season.starts_at)
    demanding = next(o for o in offers if o.profile == "demanding")
    contract = sign_offer(team, demanding.pk, at=season.starts_at)

    for week, points in zip(weeks, [0, 50, 5]):
        pay_sponsorship(week, points_by_team={team.pk: points})

    for entry in LedgerEntry.objects.filter(team=team, kind=LedgerEntry.Kind.SPONSORSHIP):
        assert contract.floor_amount <= entry.amount <= contract.ceiling_amount


def test_no_settled_week_pays_the_baseline(db, team, season, weeks):
    offers = ensure_offer_round(team, season, at=season.starts_at)
    contract = sign_offer(team, offers[0].pk, at=season.starts_at)

    # weeks[0] is week 1 — no prior settled week this season.
    pay_sponsorship(weeks[0], points_by_team={team.pk: 25})

    entry = LedgerEntry.objects.get(team=team, kind=LedgerEntry.Kind.SPONSORSHIP, week=weeks[0])
    assert entry.amount == contract.weekly_base


# ── sponsor_gap (#161) ────────────────────────────────────────────────────


def test_gap_is_the_best_floor_waiting(db, team, season):
    ensure_starting_fanbase(team, at=season.starts_at)
    offers = ensure_offer_round(team, season, at=season.starts_at, rng=random.Random(1))
    assert sponsor_gap(team, season) == max(o.floor_amount for o in offers) > 0


def test_no_gap_once_signed(db, team, season):
    offers = ensure_offer_round(team, season, at=season.starts_at, rng=random.Random(1))
    sign_offer(team, offers[0].pk, at=season.starts_at)
    assert sponsor_gap(team, season) is None


def test_gap_with_no_round_yet_is_zero(db, team, season):
    assert sponsor_gap(team, season) == 0


def test_voided_contract_leaves_a_gap(db, team, season):
    offers = ensure_offer_round(team, season, at=season.starts_at, rng=random.Random(1))
    sign_offer(team, offers[0].pk, at=season.starts_at)
    void_sponsorship(team, at=season.starts_at + timedelta(weeks=1))
    assert sponsor_gap(team, season) == 0


def test_contract_in_another_season_does_not_count(db, team, season, other_season):
    offers = ensure_offer_round(team, season, at=season.starts_at, rng=random.Random(1))
    sign_offer(team, offers[0].pk, at=season.starts_at)
    assert sponsor_gap(team, other_season) == 0
