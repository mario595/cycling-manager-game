"""Recording departures (#158, #162; riders/README.md, *Departures*).

Each function is called by the code that moves the rider, inside the same
transaction, so a departure exists exactly when the move does. Callers pass
the team explicitly, because by the time a move is saved the rider's own
`team` or `development_squad` no longer says where they came from.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping

from .models import Departure, Rider


def record_departures(
    riders: Iterable[Rider], *, team_by_rider: Mapping[int, int], kind: str, at,
) -> int:
    """Write one departure per rider in `riders` whose pk is in
    `team_by_rider`, against that team id. Returns how many were written.

    Riders missing from the map are skipped rather than refused: a caller
    passes every candidate it moved, and a rider with no team to have left
    (a free agent retiring, say) has nothing to report to anyone.
    """
    rows = [
        Departure(
            team_id=team_by_rider[rider.pk],
            rider=rider,
            rider_name=rider.name,
            speciality=rider.speciality,
            age=rider.age,
            kind=kind,
            at=at,
        )
        for rider in riders
        if team_by_rider.get(rider.pk) is not None
    ]
    Departure.objects.bulk_create(rows)
    return len(rows)


def record_sale(rider: Rider, *, seller, buyer, fee: int, at) -> Departure:
    """Write the departure for `rider` sold at auction by `seller` to
    `buyer` for `fee`. A forced sale (#27) is recorded the same way: the
    rider left the roster when listed, but the sale is what the manager
    learns about after the fact."""
    return Departure.objects.create(
        team=seller,
        rider=rider,
        rider_name=rider.name,
        speciality=rider.speciality,
        age=rider.age,
        kind=Departure.Kind.SOLD,
        at=at,
        buyer=buyer,
        fee=fee,
    )


def record_unsold_forced_sale(rider: Rider, *, seller, at) -> Departure:
    """Write the departure for `rider`, whose forced sale (#27) by `seller`
    ended with no buyer (#170). The listing was the manager's click and is
    not recorded; the rider left the roster then, but the auction ends while
    the manager may be away, and that is when they become a free agent."""
    return Departure.objects.create(
        team=seller,
        rider=rider,
        rider_name=rider.name,
        speciality=rider.speciality,
        age=rider.age,
        kind=Departure.Kind.UNSOLD,
        at=at,
    )
