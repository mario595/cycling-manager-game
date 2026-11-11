# Report a problem — Implementation Plan

**Spec:** `specs/report-a-problem.md` · **Issue:** #131 · **Status:** approved
**Apps touched:** `feedback/` (new), `api/`, `frontend/`, `config/settings/base.py`

## Context you need

Beta testers, LLM agents first and humans later, need one channel to report
what is broken. Nothing exists for it today: no model, no endpoint, no button.

- **Auth.** `REST_FRAMEWORK` in `config/settings/base.py` uses
  `SessionAuthentication` with `IsAuthenticated` as the default permission.
  API tokens are #130 and are **not built**. This feature must not depend on
  them: a plain `IsAuthenticated` view works for both, and picks tokens up for
  free when #130 adds an authentication class. See `api/README.md`,
  *Authentication*, including CSRF: the SPA's `writeJson` in
  `frontend/src/api.ts` already sends `X-CSRFToken`.
- **Context sources.** The user's team is `api.views.team_for(user)` (returns
  `None` for a team-less user). The game's time is `world.services.now()`,
  which is the *game* clock: under `MockClock` on staging it runs far ahead of
  the wall clock. Where the world is in its season is
  `schedule.services.current_position(at)`, a `Position(state, season, week)`
  where `season`/`week` may be `None`.
- **Dependency direction** (`AGENTS.md`). Only `api/` and `world/` may import
  everything. A new app may depend on `core`, `accounts`, `teams`, but nothing
  may import `api/`.
- **Frontend frame.** Every route, including `/login`, `/register` and
  `/claim`, renders inside `frontend/src/components/Layout.tsx`. Styling is
  inline `style={{}}` with colours from `src/theme.ts` (`frontend/README.md`,
  *Conventions*).

## Goal

1. `POST /api/feedback/reports/` stores a report with category, text and the
   context the server works out itself (author, team, season, week, game time,
   real time) plus the location the caller sends.
2. `GET /api/feedback/reports/` lists the caller's own reports with outcome and
   issue link, never the triage note and never anyone else's.
3. More than 20 reports in 24 real hours is refused with a 429 and a retry time.
4. Staff triage in Django admin: filter, set outcome, attach issue link, note.
5. A **Report a problem** button sits on every logged-in screen and opens a form
   over it.

## Design decisions (settled — implement these, do not substitute)

1. **A new app, `feedback/`.** Not `accounts/`: `accounts/` sits at the root of
   the dependency graph and a report points at a team. `feedback -> core,
   accounts, teams`, and both FKs are **string references**
   (`settings.AUTH_USER_MODEL`, `"teams.Team"`), so `feedback/models.py`
   imports neither app — the pattern `staff.TrainingWeekReport.week` uses.
2. **`api/` gathers the context; `feedback/` only stores it.**
   `feedback.services.submit_report` takes team, season and week as plain
   arguments. Do not import `world` or `schedule` into `feedback/` to look them
   up there: `feedback -> world` would break the rule that nothing imports
   `world/`.
3. **Context is a snapshot, never a live join.** Store `season_number`,
   `week_number` as integers and `team_name` as text, alongside the `team` FK.
   **Load-bearing:** the spec says a report keeps the team it was filed against
   even after the team is released or claimed by someone else. The FK alone
   satisfies that (the `Team` row survives a change of manager), and
   `team_name` covers the team being renamed, which a claim does. Do **not**
   read the team through `author.team` when displaying a report — that is the
   author's *current* team.
4. **Two clocks, both recorded.** `game_time` is `world.services.now()` at
   submission. `created_at` is `auto_now_add`, which is `django.utils.timezone.
   now()`, the real wall clock. Do not set `created_at` from the game clock;
   on staging the two differ by days within hours. The game clock always has a
   time, so `game_time` is always filled; `season_number`/`week_number` are
   empty off-season and before the first season, exactly as the spec says.
5. **The daily cap counts real time, not game time:** 20 reports in the
   rolling 24 real hours before now, per author, as a module constant
   `DAILY_REPORT_LIMIT = 20` in `feedback/services.py`. An agent on the
   accelerated clock lives through a game week every 7 real hours; counting
   game days would let it file 20 every hour. The check is a count followed by
   an insert with no lock, so two simultaneous posts can land one over the
   cap. That is acceptable for a cap meant to stop a runaway loop; do not add
   row locking for it.
6. **429 with a `retry_at`.** Refusing at the cap raises
   `ReportLimitReached(retry_at)`, where `retry_at` is the oldest counted
   report's `created_at + 24h`. The view answers `429` with
   `{"detail": "...", "retry_at": <iso>}`. Do not use DRF's throttling classes:
   they keep state in the cache, which is per-process with the default
   `LocMemCache`, so the cap would reset with every worker. The database count
   is the source of truth.
7. **Text over 4,000 characters is refused, not cut.** A serializer
   `CharField(max_length=4000)` returns a 400. The model field is a plain
   `TextField` so the limit can move without a migration. Blank or
   whitespace-only text is refused (`allow_blank=False`, DRF trims by default).
8. **Location is what the caller says, optional.** The SPA sends
   `location.pathname + location.search` captured when the button was pressed.
   An agent may send the endpoint it was looking at. Max 300 characters,
   refused above that; blank allowed. Do not fall back to `request.path`: that
   is always `/api/feedback/reports/` and says nothing.
9. **Reporters never see the triage note.** Two serializers would be
   overkill; one read serializer simply omits `triage_note`. A test asserts the
   key is absent.
10. **The reporter's list is unpaginated, newest first, capped at 100.** At 20
    a day that is five days of a runaway agent; nothing pages in this API yet.
11. **Admin is the triage tool.** Reporter-written fields and context are
    read-only; only `status`, `github_issue_url` and `triage_note` are
    editable. Staff cannot add reports through admin (`has_add_permission`
    returns `False`), since a report with hand-typed context would be a lie.
    Two bulk actions: mark triaged, mark dismissed.
12. **The button is a fixed floating button in `Layout`,** rendered only when
    `me.authenticated`. Layout wraps `/login` and `/register` too, so the
    check is what keeps it off them. A fixed button works on both the desktop
    sidebar layout and the mobile drawer layout without touching either.

## Data model

`feedback/models.py` (**new**), one model, migration `feedback/migrations/0001_initial.py`.

```python
class Report(models.Model):
    class Category(models.TextChoices):
        BUG = "bug", "Bug"
        LOOKS_WRONG = "looks_wrong", "Looks wrong"
        BALANCE = "balance", "Balance"
        SUGGESTION = "suggestion", "Suggestion"

    class Status(models.TextChoices):
        NEW = "new", "New"
        TRIAGED = "triaged", "Triaged"
        DISMISSED = "dismissed", "Dismissed"
```

| Field | Type | Null/blank | Default | Notes |
|---|---|---|---|---|
| `author` | FK `settings.AUTH_USER_MODEL`, `on_delete=CASCADE`, `related_name="reports"` | no | — | Spec: reports go with a deleted account. |
| `category` | `CharField(max_length=20, choices=Category)` | no | — | |
| `text` | `TextField` | no | — | Length limited in the serializer (D7). |
| `location` | `CharField(max_length=300, blank=True)` | blank | `""` | D8. |
| `team` | FK `"teams.Team"`, `on_delete=SET_NULL`, `related_name="+"` | null, blank | `None` | Team at submission. |
| `team_name` | `CharField(max_length=100, blank=True)` | blank | `""` | Snapshot (D3). Match `Team.name`'s max_length — check it. |
| `season_number` | `PositiveIntegerField` | null, blank | `None` | Empty off-season. |
| `week_number` | `PositiveIntegerField` | null, blank | `None` | Empty off-season. |
| `game_time` | `DateTimeField` | no | — | D4. |
| `created_at` | `DateTimeField(auto_now_add=True, db_index=True)` | no | — | Real time. Indexed for the cap's count and the ordering. |
| `status` | `CharField(max_length=20, choices=Status)` | no | `Status.NEW` | |
| `github_issue_url` | `URLField(blank=True)` | blank | `""` | |
| `triage_note` | `TextField(blank=True)` | blank | `""` | Staff only. |

`Meta.ordering = ["-created_at"]`; `Meta.indexes = [Index(fields=["author", "created_at"])]` for the cap query.

## feedback/services.py (new)

```python
DAILY_REPORT_LIMIT = 20
LIMIT_WINDOW = timedelta(hours=24)

class ReportLimitReached(Exception):
    def __init__(self, retry_at: datetime): ...

def submit_report(
    author, *, category: str, text: str, location: str,
    team, season_number: int | None, week_number: int | None,
    game_time: datetime,
) -> Report:
    """Raise ReportLimitReached if `author` already has DAILY_REPORT_LIMIT
    reports created in the last LIMIT_WINDOW of real time; otherwise create
    and return the report, with team_name copied from team."""

def reports_for(author, limit: int = 100) -> QuerySet[Report]: ...
```

The window is `timezone.now() - LIMIT_WINDOW`, the **real** clock. `retry_at`
is the earliest `created_at` inside the window plus `LIMIT_WINDOW`.

## feedback/admin.py (new)

`ReportAdmin`: `list_display = ("created_at", "category", "status", "author",
"team_name", "season_number", "week_number", "short_text")`; `list_filter =
("status", "category", "team")`; `search_fields = ("text", "author__email",
"team_name")`; `readonly_fields` = every field but `status`,
`github_issue_url`, `triage_note`; `has_add_permission -> False`; actions
`mark_triaged`, `mark_dismissed` that call `queryset.update(status=...)`.
`list_select_related = ("author",)`. Filtering by reporter is the
`author__email` search plus clicking an author.

## api/serializers.py

```python
class ReportSerializer(serializers.Serializer):  # read
    id, category, text, location, team_name, season_number, week_number,
    game_time, created_at, status, github_issue_url
    # deliberately no triage_note (D9)

class ReportCreateSerializer(serializers.Serializer):
    category = ChoiceField(choices=Report.Category.choices)
    text = CharField(max_length=4000)                       # D7
    location = CharField(max_length=300, required=False, allow_blank=True, default="")
```

## api/views.py

`ReportsView(APIView)`, default `IsAuthenticated`.

- `get`: `ReportSerializer(reports_for(request.user), many=True)`.
- `post`: validate; `at = now()`; `position = current_position(at)`;
  `submit_report(request.user, ..., team=team_for(request.user),
  season_number=position.season.number if position.state == "in_season" else None,
  week_number=position.week.number if position.week else None, game_time=at)`.
  **Off-season, `position.season` is the season that just finished**; that is
  why the season number is gated on `state == "in_season"`, not on
  `position.season` being set. On `ReportLimitReached` return 429
  `{"detail": "You have sent 20 reports in the last 24 hours. You can send another after <retry_at>.", "retry_at": ...}`.
  Success is 201 with `ReportSerializer`.

`api/urls.py`: `path("feedback/reports/", ReportsView.as_view(), name="reports")`.

## frontend

- `src/api.ts`: `ReportCategory` union, `Report` interface,
  `createReport(category, text, location): Promise<Report>` via `writeJson`.
  The 429's `detail` comes through `errorMessageFrom` already.
- `src/components/ReportProblem.tsx` (**new**): `ReportProblemButton` (fixed,
  bottom-right, `zIndex` above the mobile header's 40 and the drawer's 55) and
  the dialog it opens: category `<select>` (default `bug`), `<textarea>`
  (required, `maxLength={4000}`), Cancel and Send. The location is read from
  `useLocation()` **when the button is pressed** and held in state, so it is
  the screen underneath, not whatever changes later. Send is disabled while
  the text is blank or a request is in flight. On error the dialog stays open
  with the text and shows the message in `color.negative`. On success it
  closes and a short "Report received — thank you" note shows by the button
  for four seconds.
- `src/components/Layout.tsx`: render `<ReportProblemButton />` inside the
  frame when `me?.authenticated`.

## Work items

### W1 — `feedback/`: new app, model, migration, README stub
`feedback/__init__.py`, `apps.py`, `models.py`, `migrations/0001_initial.py`,
`tests/__init__.py`; add `"feedback"` to `LOCAL_APPS` (before `"world"`) and to
`testpaths` in `pyproject.toml`. **Test:** `feedback/tests/test_models.py` —
a report defaults to `new`, ordering is newest first, deleting the team leaves
the report with `team=None` and its `team_name`.

### W2 — `feedback/services.py`: submit and the daily cap
**Test:** `feedback/tests/test_services.py` — `team_name` is copied; the 21st
report in 24h raises with the right `retry_at`; a report older than 24h does
not count; another author's reports do not count.

### W3 — `feedback/admin.py`: triage
**Test:** `feedback/tests/test_admin.py` — a staff client sees the changelist
and can filter by status; the actions set status; the add page is 403; the
change form saves `status`/`github_issue_url`/`triage_note`.

### W4 — `api/`: the endpoint
**Test:** `api/test_feedback.py` (new; `tests.py` is already 160 KB) — under
`MockClock`: in-season post records season, week, team and game time; a
team-less user's post has no team; off-season leaves season and week empty;
anonymous is 403; blank text and 4,001 characters are 400; the 21st post is
429 with `retry_at`; GET lists only the caller's reports and has no
`triage_note` key; the team kept after the manager is released.

### W5 — `frontend/`: the button and the form
**Test:** `src/components/ReportProblem.test.tsx` — opens, sends category,
text and the location it was opened on; a rejected `createReport` keeps the
text and shows the message; Send disabled on blank text. Extend
`Layout.test.tsx`: the button shows for a manager and a team-less user, not
for an anonymous visitor.

### W6 — Docs and close-out
See below. Archive spec and plan with `Status: implemented`.

## Execution order

W1 → W2 → W3 → W4 → W5 → W6, committing after each. W1–W3 are backend-only and
need no API; W4 is the first point where anything is reachable; W5 needs W4's
shape.

## Documentation update (required, not optional)

- `feedback/README.md` (**new**): what the app owns, the snapshot rule (D3),
  the two clocks (D4), the cap and why it is real-time and DB-counted (D5, D6),
  what it may import, triage in admin.
- `api/README.md`: a *Feedback* entry under *What exists* for the endpoint.
- `frontend/README.md`: the button in *What exists*.
- `AGENTS.md`: a `feedback/` row in the domain table, `feedback -> core,
  accounts, teams` in the dependency graph, and the project-structure tree.

## Verification

```bash
.venv/bin/python manage.py makemigrations --check --dry-run
.venv/bin/python -m pytest
npm --prefix frontend run lint && npm --prefix frontend test && npm --prefix frontend run build
```

By hand: seed, log in as `test@mail.com`, press the button on Finances, send a
report, open `/admin/feedback/report/` as a superuser and see it with team,
season, week and location `/finances`.

The likeliest failure is recording the wrong clock: `created_at` from game
time or `game_time` from wall time. Under `RealClock` the two are equal and a
test cannot tell them apart, so W4's tests run under `MockClock` with the mock
set well away from real time and assert both values separately.

## Risks

| Risk | Mitigation |
|---|---|
| Off-season report gets the finished season's number. | Gate on `position.state == "in_season"` (W4 test). |
| `team` read live from `author.team` instead of the snapshot. | Serializer reads `team_name`; W4 test releases the team then lists. |
| Triage note leaks to the reporter. | Read serializer omits it; W4 asserts the key is absent. |
| Button shows on login/register. | Rendered only when authenticated; Layout test. |
| Cap counted on game time. | D5; W2 test uses `created_at` timestamps. |

## Open questions

None.
