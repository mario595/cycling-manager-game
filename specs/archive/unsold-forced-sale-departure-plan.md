# Plan: an unsold forced sale is a departure

**Status:** implemented
**Spec:** `specs/archive/unsold-forced-sale-departure.md` (#170)

Small enough for one commit.

## Technical decisions

- `riders.Departure.Kind` gains `UNSOLD = "unsold"`. A choices-only migration (`0018_departure_unsold_kind`); `kind` is `max_length=10`, so it fits.
- `riders/departures.py` gains `record_unsold_forced_sale(rider, *, seller, at)`, beside `record_sale`. `transfers/` already imports this module, so no new dependency edge.
- `transfers.services._resolve_unsold` is the one place both UNSOLD paths (no bid; the winner at `ROSTER_CAP`) meet, so the call goes there, branching on `auction.forced`, inside the same transaction as the status change. A forced sale's rider is never a graduate (forced sales list roster riders), so the graduate-release branch becomes the `elif`.
- The seller is `auction.seller_team`, as for a forced sale that sold: the rider's `team` has been null since listing.
- `api/serializers.DepartureSerializer.kind` adds `unsold` to its choices and help text; `frontend/src/api.ts` adds it to the union; `departureText` gets one case.

## Tests

- `transfers/tests/test_services.py`: an unsold forced sale records an `UNSOLD` departure against the seller, dated to the deadline, with no buyer or fee; the same at the winner's cap; listing a forced sale records nothing. The existing "unsold roster rider records nothing" test keeps the voluntary case pinned.
- `api/tests.py`: an `unsold` departure is served with its season and week and null buyer and fee.
- `frontend/src/departures.test.ts`: the sentence, with and without a week.

## Docs

`riders/README.md` and `transfers/README.md` (*Departures*, *Forced sales*), `api/README.md`, `frontend/README.md`, and `beta_agents/PLAYERS_GUIDE.md`.
