# Warn a manager who has not signed a sponsor

**Status:** approved
**Issue:** #161
**Domain(s):** `economy/`, `api/`, `frontend/`, `beta_agents/` (players' guide)
**One-liner:** When your team has no sponsor for the season, the game says so plainly, on the dashboard, in the sidebar and in the API, until you sign one.

## Why this exists

A team picks one sponsor per season from three offers made when the season
opens. Until it signs, it earns nothing from sponsorship. Nothing tells the
manager this is happening. One of the LLM beta testers missed the first four
weeks of season 4 and lost about $38,000 without noticing, then signed the
moment it happened to look at the Sponsors screen. A human manager who misses
the first week or two of a season, which is easy under the staging clock, has
the same problem.

Sponsorship is the largest single source of income for most teams, so an
unsigned season is one of the most expensive mistakes a manager can make. It
should also be one of the hardest to miss.

## Player experience

A new season opens. The manager logs in and the dashboard, above everything
else, shows a warning: *No sponsor this season. You are earning nothing from
sponsorship. Offers start at $9,640 a week.* with a link to Sponsors. The
Sponsors entry in the sidebar carries a small dot, so the cue is visible from
any screen. The manager follows the link, picks one of the three offers, and
both the banner and the dot are gone.

A manager who claims a team mid-season sees the same warning straight away,
since a claimed team starts without a sponsor.

A client playing through the API, like the LLM beta testers, gets the same fact
on the "who am I" answer it reads at the start of every visit, together with
the smallest offer's weekly amount. The players' guide tells it that a sponsor
must be signed every season and that this field says when one is missing.

## In scope

1. While the current season has started and the manager's team has no sponsor
   for it, the dashboard shows a warning banner above the rest of the page.
2. The banner says the team has no sponsor this season, that it is earning
   nothing from sponsorship, and the weekly amount of the smallest offer
   waiting. It links to the Sponsors screen.
3. While the same is true, the sidebar's Sponsors entry shows a dot.
4. The banner and the dot disappear once the team signs, with no reload of the
   page needed beyond the signing itself.
5. The banner cannot be dismissed.
6. A team claimed mid-season sees the warning at once.
7. The API's "who am I" answer says whether the manager's team is missing a
   sponsor for the current season and, if so, the smallest offer's weekly
   amount.
8. The players' guide says a sponsor has to be signed each season, that every
   unsigned week pays nothing, and where the API says one is missing.

## Out of scope

- **Auto-signing a team that hasn't signed after some weeks.** Deferred. It
  takes a choice away from human managers, and the warning should fix the
  real cause. Revisit if testers still miss it.
- **Back-paying unsigned weeks on a late signing.** No. A late signing costing
  money is what gives the warning meaning.
- **An estimate of money already lost.** Not shown. The smallest offer's
  weekly amount makes the stake concrete without guessing at a figure.
- **Any warning ahead of the next season**, such as "your sponsor deal ends at
  season close". Belongs to sponsor renewal (#23).
- **Email or other out-of-game notifications.** There are none in the game yet.

## Rules and edge cases

- No season declared, or between seasons: no warning. There is nothing to sign.
- A team with no manager never sees anything. Unmanaged teams sign their own
  sponsor.
- If a team has no sponsor and, for some reason, no offers waiting, the
  warning still shows, without an amount. Opening the Sponsors screen makes
  the round, as it does today.
- The warning reads the current state every time. It is not a notification
  that gets "seen" and goes away.
- The last week of a season still shows the warning. Signing then still pays
  for the weeks left.
- An insolvent team can see both banners. The insolvency banner already lists
  signing a sponsor as a way out.

## Decisions taken

- Where it shows: a dashboard banner and a dot on the sidebar's Sponsors entry. (Mario, 2026-11-25.)
- API: on the "who am I" answer, plus a line in the players' guide. (Mario, 2026-11-25.)
- Shown from season open or claim until signing, with no dismiss. (Mario, 2026-11-25.)
- The message names the smallest waiting offer's weekly amount. (Mario, 2026-11-25.)
- No auto-sign, deferred. (Mario, 2026-11-25.)
- No back-pay. (Mario, 2026-11-25.)

## Open questions

None.

## Deferred

- Auto-sign after N unsigned weeks: wait and see whether the warning alone is enough.
