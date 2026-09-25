from __future__ import annotations

from datetime import datetime, timedelta, timezone as dt_timezone

import pytest
from django.db import IntegrityError, transaction

from riders.models import Rider
from teams.models import Team
from transfers.models import Auction


def _rider(**overrides) -> Rider:
    defaults = dict(
        name="Test Rider",
        speciality=Rider.Speciality.ROULEUR,
        age=27,
        climb=50, sprint=50, flat=50, resistance=50, positioning=50,
    )
    defaults.update(overrides)
    return Rider.objects.create(**defaults)


def _auction(rider, team, *, status=Auction.Status.OPEN, **overrides) -> Auction:
    now = datetime(2027, 3, 1, 0, 0, tzinfo=dt_timezone.utc)
    defaults = dict(
        reserve_price=50_000,
        current_price=50_000,
        min_increment=2_500,
        deadline=now + timedelta(days=3),
        listed_at=now,
    )
    defaults.update(overrides)
    return Auction.objects.create(rider=rider, seller_team=team, status=status, **defaults)


def test_one_open_auction_per_rider_constraint(db):
    team = Team.objects.create(name="Team Alpha", code="ALP")
    rider = _rider(team=team)
    _auction(rider, team, status=Auction.Status.OPEN)

    with pytest.raises(IntegrityError):
        with transaction.atomic():
            _auction(rider, team, status=Auction.Status.OPEN)

    # A second auction for the same rider is fine once the first is no
    # longer open — the partial unique constraint only guards `open`.
    _auction(rider, team, status=Auction.Status.SOLD)

    assert Auction.objects.filter(rider=rider).count() == 2
