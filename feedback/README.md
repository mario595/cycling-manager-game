# Feedback — reporting a problem

## What this app owns

`feedback.Report` (#131): one report of a problem from a beta tester, human
or LLM, with the context it was sent in, and the triage that follows it. The
endpoint is `api/`'s (`POST`/`GET /api/feedback/reports/`, see
`api/README.md`); the button is `frontend/`'s
(`components/ReportProblem.tsx`); triage is Django admin, here.

The spec and plan are `specs/archive/report-a-problem.md` and
`specs/archive/report-a-problem-plan.md`.

## What `feedback/` may import

`core`, and `accounts`/`teams` by **string reference only** —
`Report.author` is `settings.AUTH_USER_MODEL` and `Report.team` is
`"teams.Team"`, so `models.py` imports neither, the same pattern as
`staff.TrainingWeekReport.week`.

It does **not** import `world/` or `schedule/`. The context a report needs —
the caller's team, the season and week, the game time — is worked out by
`api/views.py`'s `ReportsView` and passed into `submit_report` as plain
arguments. Nothing may import `world/`, and this app has no business
knowing how the season position is derived.

## Context is a snapshot

A report records where its author was **when they sent it**: `team` (FK,
`SET_NULL`), `team_name`, `season_number`, `week_number`, `game_time`,
`location`. None of it is recomputed. A team that is later released, claimed
by someone else and renamed still shows on the report under the name it had
— never read the team through `author.team`, which is the author's team
*now*. `season_number` and `week_number` are `null` off-season and before
the first season.

## Reports outlive a world reset

`seed_world --reset` (#139) truncates every world table with `CASCADE`, and
Postgres's `TRUNCATE CASCADE` empties any table holding a foreign-key
constraint into a truncated one. So `Report.team` is declared with
`db_constraint=False`: Django still treats it as a foreign key (joins,
admin, `SET_NULL` on an ordinary team delete, which Django enforces in
Python anyway), but the database holds no constraint for the truncate to
follow. `wipe_world` sets `team` to null on every report first, inside the
same transaction, because `RESTART IDENTITY` hands the old ids to new teams.
`team_name` keeps the snapshot. Do not put the constraint back.

## Two clocks

`game_time` is `world.services.now()` — the game clock, which on staging's
accelerated `MockClock` runs a game day per real hour. `created_at` is the
real wall clock (`auto_now_add`). Both are kept because a bug report on
staging needs both: *which game week* to reproduce it, *which real hour* to
find it in the logs. Never fill one from the other; under `RealClock` they
match, so only a `MockClock` test can tell a mix-up apart
(`api/test_feedback.py`).

## The daily cap

`DAILY_REPORT_LIMIT = 20` reports per author in the rolling 24 **real**
hours (`feedback/services.py`). Real hours, because an agent on the
accelerated clock lives a game week every seven real hours; counted in game
days the cap would barely bite. Past it `submit_report` raises
`ReportLimitReached(retry_at)`, the oldest counted report's `created_at`
plus 24 hours, and the API answers `429`.

The count is a database query, not DRF throttling: throttles keep state in
the cache, which is per-process with the default `LocMemCache` and would
reset with every worker. The count and the insert are not locked together,
so two simultaneous posts can land one over the cap — fine for a guard
against a runaway loop.

Text is limited to 4,000 characters by the API's serializer, refused above
that rather than cut; the column is a plain `TextField` so the limit can
move without a migration.

## Triage

`/admin/feedback/report/`, for staff. Filter by status, category, team and reporter;
search text, author email and team name. What the reporter wrote and the
captured context are read-only; only `status` (`new` → `triaged` or
`dismissed`), `github_issue_url` and `triage_note` change. Two bulk actions
mark a selection triaged or dismissed. Staff cannot add a report by hand.

The reporter sees `status` and `github_issue_url` through the API, **never
`triage_note`** — `api/serializers.py`'s `ReportSerializer` leaves it out,
and `api/test_feedback.py` asserts the key is absent.

Reports become GitHub issues by hand, deliberately: six agents noticing the
same deficit should become one issue, not six.

## Not built yet

- An in-app "my reports" screen (the list is API-only).
- A triage agent that groups duplicate reports.
- Spanish copy for the button and form (#137).
