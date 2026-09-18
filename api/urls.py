from __future__ import annotations

from django.urls import include, path

from .views import (
    CalendarView,
    ClaimTeamView,
    ClockView,
    FinancesView,
    FireTrainerView,
    HireTrainerView,
    MeView,
    PositionView,
    RaceResultsView,
    RiderListView,
    SquadView,
    StaffView,
    StandingsView,
    TrainingView,
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
    path("teams/claim/", ClaimTeamView.as_view(), name="claim-team"),
    path("staff/", StaffView.as_view(), name="staff"),
    path("staff/trainer/hire/", HireTrainerView.as_view(), name="hire-trainer"),
    path("staff/trainer/fire/", FireTrainerView.as_view(), name="fire-trainer"),
    path("staff/training/", TrainingView.as_view(), name="training"),
    path("economy/finances/", FinancesView.as_view(), name="finances"),
]
