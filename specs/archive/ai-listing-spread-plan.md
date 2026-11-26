# AI listings spread across the week: implementation plan

**Status:** implemented
**Spec:** `specs/ai-listing-spread.md` (#172)
**Touches:** `world/ai_market.py`, `world/services.py` (the tick), their tests, `world/README.md`

## What changes, in one paragraph

`list_ai_riders` stops being a week-boundary step. The tick calls it on
**every** tick with the week the clock is in now (`schedule.services.current_position(at).week`),
and each unmanaged team lists only once the game clock has passed its own
*listing moment* inside its turn week. The week stagger is unchanged. A second
fallback rule in `pick_listing` sells a depth rider. Nothing else moves: no
model, no migration, no API, no frontend.

## Design decisions

1. **The listing moment.** For team `T` in week `W` (its turn week, by the
   unchanged `(W.number + T.pk) % AI_LISTING_EVERY_WEEKS == 0`):
   `listing_moment(T, W) = W.starts_at + timedelta(days=listing_day(T))`, with
   `listing_day(T) = (T.pk // AI_LISTING_EVERY_WEEKS * AI_LISTING_DAY_STRIDE) % 7`
   and `AI_LISTING_DAY_STRIDE = 3`. Teams that share a turn week have pks that
   differ by multiples of 4, so their `pk // 4` values are consecutive, and a
   stride of 3 (coprime with 7) walks them through days 0, 3, 6, 2, 5, 1, 4:
   seven teams per turn week before two share a day. Deterministic, like the
   week stagger, so tests are exact and the pattern is the same on every clock.
   It is game time, so 24× staging gets a listing day per game day (an hour)
   and production one per real day.
2. **Once per turn, without new state.** A team is due when
   `at >= listing_moment` and it has **no auction with `listed_at >= listing_moment`**
   (any status). That one query is the "already listed this turn" record, so
   no field is needed. A team with nothing to sell on its day is retried on
   later ticks of the same week (spec rule 4) and lists at most once.
3. **Catch-up.** The tick passes the *current* week, not the weeks it crossed.
   A tick that jumps over a team's listing moment lists once (rule 3); a tick
   that jumps over a team's whole turn week lists nothing for it, which is the
   same outcome as today's "last week crossed" rule for the skipped weeks.
   Out of season (`week is None`) nothing lists.
4. **The depth rule.** `pick_listing`'s third branch, after surplus and
   ageing: among candidates not in the top `AI_NEED_RANK` of their speciality
   (which needs at least three of that speciality on the roster), list the
   **weakest** by `strength`, then oldest, then pk. Weakest because the AI
   keeps its better depth, and because the buyer side never wants a non-top-2
   rider, so the AI will not sell what it would buy. The `AI_MIN_ROSTER`
   floor in `list_ai_riders` already stops a sale that leaves fewer than ten.
5. **Order in the tick is unchanged**: sign free agents (week-crossing ticks
   only), then list, then bid. Listing simply drops its `if weeks:` guard.
6. **Cost.** Every tick now runs the listing pass. A team out of its turn week
   or before its moment costs no query (both checks are arithmetic); a due
   team costs one `exists()` before the existing queries. Ten-odd teams every
   five minutes is negligible.

## Work items

1. **`world/ai_market.py`**: add `AI_LISTING_DAY_STRIDE`, `listing_day(team)`
   and `listing_moment(team, week)`; gate each team in `list_ai_riders` on the
   moment and the once-per-turn query; add the depth branch to `pick_listing`.
   Update the module and function docstrings.
   *Tests* (`world/tests/test_ai_market.py`): existing listing tests call
   `list_ai_riders` at `listing_moment(team, week)`; new tests for
   before-the-moment (nothing), at-the-moment (lists), a second call in the
   same week after a listing (nothing, even once the first auction has
   resolved), a retry later in the week when the first attempt had nothing,
   `listing_day` spreading four teams of one turn over four distinct days,
   and `pick_listing`'s depth branch (weakest depth rider; nothing when every
   speciality has at most two).
2. **`world/services.py`**: call `list_ai_riders(current_position(at).week, at)`
   on every tick when a week is current.
   *Tests* (`world/tests/test_tick.py`): the catch-up test moves its clock past
   the team's moment; a new test lists on a tick that crosses **no** week.
3. **Docs**: `world/README.md` (tick step 4, *Selling*, the constants table),
   spec and plan to `specs/archive/` with `Status: implemented`.

## Verification

`pytest world` while iterating, then the full suite once. No seed changes: the
existing seeds already make AI teams with sellable rosters.
