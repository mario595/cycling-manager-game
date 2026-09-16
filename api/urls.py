from __future__ import annotations

from django.urls import include, path

from .views import (
    CalendarView,
    ClockView,
    MeView,
    PositionView,
    RaceResultsView,
    RiderListView,
    SquadView,
    StandingsView,
)

app_name = "api"

urlpatterns = [
    path("accounts/", include("accounts.urls")),
    path("accounts/me/", MeView.as_view(), name="me"),
    path("world/clock/", ClockView.as_view(), name="clock"),
    path("schedule/position/", PositionView.as_view(), name="position"),
    path("schedule/calendar/", CalendarView.as_view(), name="calendar"),
    path("racing/races/<int:race_id>/squad/", SquadView.as_view(), name="squad"),
    path("racing/races/<int:race_id>/results/", RaceResultsView.as_view(), name="race-results"),
    path("competitions/standings/", StandingsView.as_view(), name="standings"),
    path("riders/", RiderListView.as_view(), name="riders"),
]
