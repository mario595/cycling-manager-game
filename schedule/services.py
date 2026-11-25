"""Where the world is in its season, and the exactly-once record of season
boundaries. See `schedule/README.md`, *Derived, not stored*.

Both public functions take `at` as a required parameter and never default it
from the clock: `schedule/` must not import `world/` (`AGENTS.md`'s
dependency direction). Callers (`api/`, `world/`) pass `world.services.now()`
in themselves.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from django.db import IntegrityError, transaction

from .models import Season, SeasonTransition, Week, WeekTransition


@dataclass(frozen=True)
class Position:
    state: str  # "in_season" | "off_season" | "no_season"
    season: Season | None
    week: Week | None


def current_position(at: datetime) -> Position:
    """Where the world is, derived entirely from `at`. No stored pointer —
    see schedule/README.md: a missed tick must never be able to make the
    game display the wrong week.
    """
    season = Season.objects.filter(starts_at__lte=at, ends_at__gt=at).first()
    if season is not None:
        week = season.weeks.filter(starts_at__lte=at, ends_at__gt=at).first()
        return Position(state="in_season", season=season, week=week)

    finished = Season.objects.filter(ends_at__lte=at).order_by("-ends_at").first()
    if finished is not None:
        return Position(state="off_season", season=finished, week=None)

    return Position(state="no_season", season=None, week=None)


def season_and_week_of(moments: list[datetime]) -> list[tuple[int | None, int | None]]:
    """`(season number, week number)` for each of `moments`, by the same rule
    as `current_position`, in two queries however many there are.

    In a season, both numbers, with the week None only if the season's weeks
    leave a gap. After a season has ended and before the next starts, that
    season with no week, which is `current_position`'s `off_season`. Before
    any season, `(None, None)`. For a reader that places many timestamps at
    once (a team's departures, #158) where `current_position` would cost
    three queries per row.
    """
    if not moments:
        return []
    seasons = list(Season.objects.prefetch_related("weeks").order_by("starts_at"))
    placed = []
    for at in moments:
        current = next((s for s in seasons if s.starts_at <= at < s.ends_at), None)
        if current is not None:
            week = next(
                (w for w in current.weeks.all() if w.starts_at <= at < w.ends_at), None,
            )
            placed.append((current.number, week.number if week else None))
            continue
        finished = [s for s in seasons if s.ends_at <= at]
        if finished:
            placed.append((max(finished, key=lambda s: s.ends_at).number, None))
        else:
            placed.append((None, None))
    return placed


def process_transitions(at: datetime) -> list[SeasonTransition]:
    """Record every season boundary crossed at or before `at` that has not
    been recorded yet, oldest first.

    Exactly-once comes from the unique constraint on (season, kind), NOT
    from the existence checks below — those only keep the common case cheap.
    A concurrent tick loses the race at the INSERT and moves on.

    Today a transition is only a row. It is the hook later features
    (promotion/relegation, contracts, salaries) attach to; it ships empty
    on purpose — see specs/season.md, "Out of scope".
    """
    written: list[SeasonTransition] = []
    plans = [
        (
            SeasonTransition.Kind.OPENED,
            Season.objects.filter(starts_at__lte=at)
            .exclude(transitions__kind=SeasonTransition.Kind.OPENED)
            .order_by("starts_at"),
        ),
        (
            SeasonTransition.Kind.CLOSED,
            Season.objects.filter(ends_at__lte=at)
            .exclude(transitions__kind=SeasonTransition.Kind.CLOSED)
            .order_by("ends_at"),
        ),
    ]
    for kind, queryset in plans:
        for season in queryset:
            moment = season.starts_at if kind == SeasonTransition.Kind.OPENED else season.ends_at
            try:
                with transaction.atomic():
                    written.append(
                        SeasonTransition.objects.create(
                            season=season, kind=kind, occurred_at=moment,
                        )
                    )
            except IntegrityError:
                # Another tick got there first. Correct outcome, not an error.
                continue
    return written


def process_week_transitions(at: datetime) -> list[WeekTransition]:
    """Record every week boundary opened at or before `at` that has not
    been recorded yet, oldest first.

    Exactly-once comes from the unique constraint on `week`, NOT from the
    exclude() below — that only keeps the common case cheap. A concurrent
    tick loses the race at the INSERT and moves on. One atomic() per
    create, never one around the loop: an IntegrityError poisons the
    enclosing transaction in Django. Same shape as process_transitions;
    see schedule/README.md, *Week transitions*.
    """
    written: list[WeekTransition] = []
    weeks = (
        Week.objects.filter(starts_at__lte=at)
        .exclude(transitions__isnull=False)
        .order_by("starts_at")
    )
    for week in weeks:
        try:
            with transaction.atomic():
                written.append(
                    WeekTransition.objects.create(week=week, occurred_at=week.starts_at)
                )
        except IntegrityError:
            # Another tick got there first. Correct outcome, not an error.
            continue
    return written


def weeks_opened_between(start: datetime, end: datetime) -> int:
    """In-season weeks that opened in `[start, end)`.

    Counting Week rows rather than dividing a timedelta by seven days is
    what makes "off-season doesn't count" (#63) fall out for free: weeks
    only exist inside a declared season, so a gap between seasons
    contributes no rows regardless of how much real or game time it spans.

    `starts_at__gte` (not `__gt`) is deliberate: someone active at the
    exact instant a week opened has seen that week.

    Public because two apps need it with different intents — `world/`
    for inactivity and free-agent expiry, `api/` for the claim-cooldown
    release exemption — and `schedule/` owns week counting (AGENTS.md's
    dependency direction).
    """
    return Week.objects.filter(starts_at__gte=start, starts_at__lt=end).count()


def weeks_ago_cutoff(boundary: datetime, n: int) -> datetime | None:
    """The `starts_at` of the n-th newest in-season week opening before
    `boundary`, or None if fewer than n weeks have opened by then.

    "At least n in-season weeks have opened in `[since, boundary)`" is
    monotone in `since`, so it has a single cutoff: a date qualifies iff it
    is at or before this one. One query answers it for every rider at once,
    where counting per rider would be a COUNT each.

    Public because two apps must agree on it exactly (#34): `world/` uses it
    to graduate squad riders and close graduates' windows at a boundary, and
    `api/` to project who will have graduated by the next intake week. Two
    copies of the rule would be two answers to "has this rider graduated by
    then", and the squad screen's warning would drift from what the tick does.
    """
    opened = list(
        Week.objects.filter(starts_at__lt=boundary)
        .order_by("-starts_at")
        .values_list("starts_at", flat=True)[:n]
    )
    if len(opened) < n:
        return None
    return opened[n - 1]
