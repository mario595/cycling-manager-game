# Cancel listings on claim — Implementation Plan

**Spec:** `specs/cancel-listings-on-claim.md` · **Issue:** #114 · **Status:** proposed
**Apps touched:** `transfers/`, `api/`, `world/` (tests only)

## Context you need

A **claim** (`teams.services.claim_team`, `teams/README.md`, *Claiming a team*)
hands a user an unmanaged team. It releases the team's whole roster to the
free-agent pool (`team = NULL`, `unattached_since = at`) and generates a fresh
one. `teams/` may not import `transfers/`, so anything auction-related
happens in the caller: `api.views.ClaimTeamView.post` (`api/views.py:387`)
wraps `claim_team(...)` and `transfers.services.withdraw_bids(team, at=at)` in
one `transaction.atomic()`. That handles the **purchase** side (#30). See
`transfers/README.md`, *Withdrawal on claim*.

The **sale** side is the bug. An `Auction` (`transfers/models.py`) has
`rider`, `seller_team`, `status` (`open`/`sold`/`unsold`/`cancelled`) and
`resolved_at`. AI teams list riders (`world/ai_market.py`). When such a team
is claimed, its `OPEN` auctions survive, still pointing `seller_team` at the
now-managed team, for a rider who is now a free agent. Today:

- `AuctionMarketView` shows it with `is_own_listing = True` to the new manager.
- `world.ai_market._biddable_auctions` filters `seller_team__manager__isnull=False`,
  so the AI now treats it as a human listing and bids the reserve on it,
  which counts against that AI team's headroom (`_buyers()` sums live top bids
  on `OPEN` auctions).
- `transfers.services.free_agents()` also lists the rider, so they can be
  signed while their auction is still open.
- At the deadline `resolve_auction` sees the rider left the seller's roster
  and cancels it. No money moves wrongly.

`transfers.services.cancel_open_auctions(rider_ids, *, at)` (#42, used for
retirements) already does exactly the cancellation we want — one UPDATE to
`CANCELLED` with `resolved_at = at`, no money moved — but keyed by rider ids.

Repo rules that bind this work: `transfers -> riders` only (it must not import
`teams/`, `economy/` or `world/`); `teams/` must not import `transfers/`;
only `api/` and `world/` orchestrate across apps.

## Goal

1. A successful claim leaves the claimed team with **zero** `OPEN` auctions
   where it is `seller_team`; each one becomes `CANCELLED` with
   `resolved_at = at` (the claim's game time).
2. That happens inside the claim's transaction — a failed claim cancels
   nothing, and no observer ever sees the claimed team with an open listing.
3. No money moves; bids on those auctions are left untouched as history.
4. Everything downstream (market screen, `/auctions/mine/`, AI headroom, AI
   bidding) reacts with **no code change**, because each already filters on
   `status = OPEN`.

## Design decisions (settled — implement these, do not substitute)

1. **New service `transfers.services.cancel_listings(team, *, at) -> int`,
   keyed by `seller_team`.** Do **not** reuse `cancel_open_auctions` by
   collecting rider ids in the view. By the time the view runs, `claim_team`
   has already detached the riders from the team, so "the team's riders"
   is the *new* roster — collecting ids from `team.riders` returns the wrong
   riders and silently cancels nothing. Collecting them *before* the claim
   is fragile ordering in a view. The listing belongs to the seller; key it
   by the seller. It is the name the issue proposed, and it pairs with
   `withdraw_bids(team, *, at)` in shape.

2. **One UPDATE, mirroring `cancel_open_auctions`:**
   `Auction.objects.filter(seller_team=team, status=OPEN).update(status=CANCELLED, resolved_at=at)`.
   No row locking loop. The conditional UPDATE is atomic per row in Postgres;
   a concurrent `place_bid` holds the auction row lock and re-checks status,
   so whichever commits second sees the other's result. `withdraw_bids` needs
   `select_for_update` because it reads bids and computes a price; this does
   not.

3. **Do not withdraw the bids on the cancelled auctions.** `withdrawn_at`
   means "a claim took this team's bid back" (#30). These bids were not taken
   back — the auction ended. Every reader that matters filters
   `auction__status=OPEN`, so the bids already stop counting: the AI's
   `committed`, `MyBidsView`, `AuctionMarketView`. Stamping them would also
   be wrong for history. Same reasoning as
   `test_cancel_open_auctions_keeps_bid_history`.

4. **Call it from `ClaimTeamView`, after `withdraw_bids`, inside the same
   `with transaction.atomic():` block.** Not inside `claim_team` — `teams/`
   may not import `transfers/`. Order relative to `withdraw_bids` does not
   matter (a team cannot bid on its own listing — `SelfBid`), but keep it
   after so the diff is one line and both transfer steps sit together.

5. **No status reason, no new enum value, no migration.** `CANCELLED` is
   what the spec settled on (*Out of scope*: no distinct "cancelled by claim").

6. **`seed_teams --claim-for` and `release_team` are not touched.** Seeding
   runs on fresh teams with no listings and `teams/` cannot import
   `transfers/`; release deliberately touches nothing but the manager link
   (spec, *Decisions taken*). Do not "helpfully" add either.

7. **Do not touch `updated_at`.** `QuerySet.update()` bypasses `auto_now`.
   `cancel_open_auctions` already leaves it as is; matching it keeps the two
   cancellation paths identical. Nothing reads `updated_at` for auctions.

## Data model

No change. No migration.

## `transfers/services.py`

Add, directly after `withdraw_bids` (line ~411) so the two claim-time
helpers sit together:

```python
def cancel_listings(team, *, at) -> int:
    """Cancel every OPEN auction `team` is selling — no money moves (bids are
    never escrowed). Returns auctions cancelled.

    Called on a claim (#114), the sale-side counterpart to withdraw_bids: the
    claim has already released the listed riders to the free-agent pool, so a
    listing left open would show the new manager a sale they never made and
    invite bids on a rider nobody is selling. Bids are left as they are —
    they were not withdrawn, the auction ended — and every reader that counts
    them filters on an OPEN auction.
    """
    return Auction.objects.filter(
        seller_team=team, status=Auction.Status.OPEN,
    ).update(status=Auction.Status.CANCELLED, resolved_at=at)
```

## `api/views.py`

- Add `cancel_listings` to the `from transfers.services import (...)` block
  (alphabetical, so it goes before `free_agents`).
- In `ClaimTeamView.post`, inside the existing `with transaction.atomic():`,
  after `withdraw_bids(team, at=at)`:

```python
                withdraw_bids(team, at=at)
                cancel_listings(team, at=at)
```

- Update the view's docstring with one sentence: the claim, the bid
  withdrawal and the listing cancellation share one transaction.

The `except` clauses stay **outside** the `atomic()` block, as they are now —
that is what makes a raise roll the whole claim back.

## Work items

### W1 — `transfers/services.py`: add `cancel_listings`

Add the function above. Tests in `transfers/tests/test_services.py`
(import `cancel_listings` in the existing import block; use the file's
`_rider` helper and `claimed_at` fixture):

- `test_cancel_listings_cancels_the_teams_open_listings` — seller lists two
  riders; a second team bids on one. Call `cancel_listings(seller, at=t)`.
  Assert return `2`, both `CANCELLED`, both `resolved_at == t`.
- `test_cancel_listings_leaves_other_sellers_and_closed_auctions_alone` —
  another team's `OPEN` listing stays `OPEN` with `resolved_at is None`;
  the seller's own `SOLD` and `UNSOLD` auctions keep their status and
  `resolved_at` (set status by hand the way
  `test_cancel_open_auctions_cancels_only_open` does).
- `test_cancel_listings_keeps_bids_live_as_history` — after cancelling, the
  bid still exists with `withdrawn_at is None`, same amount and bidder.
  **Load-bearing**: this is the test that stops someone "tidying up" by
  stamping `withdrawn_at` (Design decision 3).
- `test_cancel_listings_with_nothing_open_returns_zero` — a team with no
  listings: returns `0`; a second call after a cancel also returns `0`.

### W2 — `api/views.py`: call it in `ClaimTeamView`

Make the change above. Tests in `api/tests.py`, next to
`test_claim_withdraws_the_claimed_teams_standing_bids` (line ~1630):

- `test_claim_cancels_the_claimed_teams_open_listings` — create the
  claimable seller **first** as an unmanaged team (claim takes the
  lowest-pk unmanaged team), give it a rider via `_market_rider`, list it
  with `list_for_auction`, and have `market_team` (managed, from the
  fixture) bid the reserve. POST the claim with `claim_client`. Assert:
  201; the auction is `CANCELLED` with a non-null `resolved_at`; the rider's
  `team_id is None` (still a free agent — spec item 4); and, through
  `market_client`, `GET /api/transfers/auctions/` and
  `GET /api/transfers/auctions/mine/` no longer contain the auction's id.
  Careful: `market_team` must not be the claimable team — it has a manager,
  so it is not.
- `test_claim_rolls_back_listing_cancellation_when_it_fails` — same setup;
  `monkeypatch.setattr("api.views.cancel_listings", _explode)`; assert the
  POST raises `RuntimeError`, the seller still has no manager and its old
  name/code, and the auction is still `OPEN` with `resolved_at is None`.
  Model it on `test_claim_rolls_back_the_withdrawal_when_it_fails`.
  **Load-bearing**: proves the call is inside the `atomic()` block (spec
  item 7). A call placed after the `with` would pass the first test and
  fail this one.

### W3 — `world/tests/test_ai_market.py`: prove the AI side needs no change

No production change. Tests only, using the file's `_seller`, `_ai_team`,
`_ai_roster`, `_saved_rider` helpers:

- `test_ai_ignores_a_listing_cancelled_by_claim` — an unmanaged team lists a
  rider; give that team a manager (simulating the claim's effect on
  `seller_team__manager`); `cancel_listings(team, at=now())`; an AI team that
  wants the rider runs `place_ai_bids`. Assert `(0, "")` and no bids.
  Before this ticket the same set-up (minus the cancel) gets a bid.
- `test_ai_headroom_is_freed_when_a_listing_it_bid_on_is_cancelled` — model
  it on `test_ai_commitments_reduce_headroom_across_ticks`: AI with a
  balance of `2 * reserve`, bids on the first listing; `cancel_listings`
  on the seller; list a second rider with the same reserve; `place_ai_bids`
  places `1` on the second. Spec item 6.

### W4 — Docs, spec and plan status, archive

See *Documentation update*. Set both `Status:` lines to `implemented` and
move `specs/cancel-listings-on-claim.md` and this plan to `specs/archive/`.

## Execution order

1. **W1** — the service alone, green in isolation. Commit.
2. **W2** — wire it into the claim. Commit. This is the fix; after it the
   bug is gone.
3. **W3** — AI-side regression tests. Commit. They exercise W1 directly, so
   they could come earlier, but they read as "what the fix already gives
   us" once W2 is in.
4. **W4** — docs and archive. Commit.

Run the full suite (`/home/mario/dev/cycling-manager/.venv/bin/python -m pytest`)
before each commit; nothing outside the touched tests should move.

## Documentation update (required, not optional)

- **`transfers/README.md`**
  - Top list (line ~22–25): add `services.cancel_listings` to the auctions
    bullet.
  - Rename *Withdrawal on claim* to *Withdrawal and cancellation on claim*
    and add a paragraph: a claim also cancels every `OPEN` auction the team
    is selling via `cancel_listings(team, *, at)` (#114); keyed by
    `seller_team` because the claim has already detached the riders; no
    money moves; bids are left un-withdrawn because they were not taken
    back, and every reader filters on `OPEN`; called in the same
    transaction as `withdraw_bids`.
  - *Cancellation* bullet under *Auctions*: note there are now two callers
    of cancellation, retirement (`cancel_open_auctions`) and claim
    (`cancel_listings`).
- **`api/README.md`**, the `POST /api/teams/claim/` entry (line ~328): the
  transaction covers `withdraw_bids` **and** `cancel_listings`; a new
  manager inherits neither the team's bids nor its listings.
- **`teams/README.md`**, *Claiming a team*: the "`ClaimTeamView` widens that
  transaction…" paragraph names listing cancellation too; the
  "`seed_teams --claim-for` does not withdraw" paragraph says it does not
  cancel listings either, for the same reasons.
- **`AGENTS.md`**, the `transfers/` row: after the `withdraw_bids` clause,
  add "and `cancel_listings`, which cancels a claimed team's open listings
  in the same transaction (#114)". (`CLAUDE.md` is a symlink — edit
  `AGENTS.md`.)
- **`specs/roadmap.md`**: mark #114 done in its row and in the dependency
  graph line (`#114 claim cancels listings` → ✅), matching how other
  shipped items are marked there.

## Verification

Unit and API tests above, then by hand in this worktree's database:

```bash
PY=/home/mario/dev/cycling-manager/.venv/bin/python
$PY scripts/dev_db.py && $PY manage.py migrate
$PY manage.py seed_user && $PY manage.py seed_teams --claim-for test@mail.com
$PY manage.py load_season seasons/season-1.example.json
```

Then in `manage.py shell`, as an unmanaged team, `list_for_auction` one of
its riders and have the demo account's team `place_bid` on it. Register a
second user in the SPA and claim a team until you get that one (or make it
the lowest-pk unmanaged team first). Check:

1. The new manager's Transfers → auctions tab shows no listing of their own.
2. The demo account's Transfers tab no longer shows the auction, and its
   outbid/my-bids list does not include it.
3. The listed rider appears in the free-agent pool exactly once, with a
   signing fee.
4. `Auction.objects.get(pk=...)` is `cancelled` with `resolved_at` set to the
   claim's game time; its bid row still exists, `withdrawn_at` null.
5. The demo team's balance and the claimed team's ledger show no entry from
   the cancellation.

**Likeliest failure:** the call lands outside the `atomic()` block, or the
cancellation is keyed by `team.riders` after the claim. The first is caught
by `test_claim_rolls_back_listing_cancellation_when_it_fails`; the second by
`test_claim_cancels_the_claimed_teams_open_listings` (the auction would stay
`OPEN`). Before writing W2, run the W2 API test against unchanged code and
confirm it **fails** — a test that passes before the fix proves nothing.

## Risks

| Risk | Mitigation |
|---|---|
| Collecting rider ids from `team.riders` after `claim_team` and passing them to `cancel_open_auctions` — returns the new roster, cancels nothing | Design decision 1; keyed by `seller_team`; W2's API test fails if done this way |
| Calling `cancel_listings` after the `with transaction.atomic():` block | W2 rollback test |
| "Cleaning up" by stamping `withdrawn_at` on the cancelled auctions' bids | Design decision 3; W1 `test_cancel_listings_keeps_bids_live_as_history` |
| Adding cancellation to `release_team` or `seed_teams` | Design decision 6; both are spec *Out of scope* |
| A tick's `resolve_auction` racing a claim on the same auction | Pre-existing and unchanged: `resolve_auction` locks the auction and rider rows; whichever transaction commits first wins, and the UPDATE's `status=OPEN` filter skips an auction already settled. No new window is introduced |
| API test claims the wrong team (claim takes the lowest-pk unmanaged team) | Create the listing seller before any other unmanaged team in the test |

## Open questions

None.
