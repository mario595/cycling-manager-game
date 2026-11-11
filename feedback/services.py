"""Submitting a report, and the daily cap on how many one account may send.

The context (team, season, week, game time) is passed in by the caller —
`api/` works it out — so this app never imports `world/` or `schedule/`.
"""

from __future__ import annotations

from datetime import datetime, timedelta

from django.db.models import QuerySet
from django.utils import timezone

from .models import Report

DAILY_REPORT_LIMIT = 20
# Real time, not game time: on staging's accelerated clock a game day passes
# every real hour, and a cap counted in game days would barely bite.
LIMIT_WINDOW = timedelta(hours=24)


class ReportLimitReached(Exception):
    """The author has already sent DAILY_REPORT_LIMIT reports in the last
    LIMIT_WINDOW. `retry_at` is when the oldest of them leaves the window."""

    def __init__(self, retry_at: datetime):
        super().__init__(f"report limit reached; retry at {retry_at.isoformat()}")
        self.retry_at = retry_at


def submit_report(
    author,
    *,
    category: str,
    text: str,
    location: str,
    team,
    season_number: int | None,
    week_number: int | None,
    game_time: datetime,
) -> Report:
    """Store a report, or raise ReportLimitReached.

    The count and the insert are not locked together, so two simultaneous
    submissions can land one over the cap. That is fine for a cap whose job
    is stopping a runaway loop, not metering.
    """
    window_start = timezone.now() - LIMIT_WINDOW
    recent = Report.objects.filter(author=author, created_at__gt=window_start)
    if recent.count() >= DAILY_REPORT_LIMIT:
        oldest = recent.order_by("created_at").values_list("created_at", flat=True).first()
        raise ReportLimitReached(oldest + LIMIT_WINDOW)

    return Report.objects.create(
        author=author,
        category=category,
        text=text,
        location=location,
        team=team,
        team_name=team.name if team is not None else "",
        season_number=season_number,
        week_number=week_number,
        game_time=game_time,
    )


def reports_for(author, limit: int = 100) -> QuerySet[Report]:
    """The author's own reports, newest first."""
    return Report.objects.filter(author=author).order_by("-created_at")[:limit]
