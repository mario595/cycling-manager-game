from __future__ import annotations

from django.urls import include, path

from .views import (
    AcknowledgeSpellView,
    CalendarView,
    ClaimTeamView,
    ClockView,
    FinancesView,
    FireTrainerView,
    FreeAgentsView,
    HireTrainerView,
    LoginView,
    MeView,
    PositionView,
    RaceDetailView,
    RaceResultsView,
    ReleaseRiderView,
    RiderListView,
    SignFreeAgentView,
    SignOfferView,
    SponsorsView,
    SquadView,
    StaffView,
    StandingsView,
    TrainingView,
)

app_name = "api"

urlpatterns = [
    # Ahead of the accounts.urls include below: this route must win so
    # that POST /api/accounts/login/ stamps last_seen_at (api/views.py's
    # LoginView), not the plain accounts.views.LoginView it subclasses —
    # see accounts/README.md, Last seen is game time.
    path("accounts/login/", LoginView.as_view(), name="login"),
    path("accounts/", include("accounts.urls")),
    path("accounts/me/", MeView.as_view(), name="me"),
    path("world/clock/", ClockView.as_view(), name="clock"),
    path("schedule/position/", PositionView.as_view(), name="position"),
    path("schedule/calendar/", CalendarView.as_view(), name="calendar"),
    path("racing/races/<int:race_id>/squad/", SquadView.as_view(), name="squad"),
    path("racing/races/<int:race_id>/results/", RaceResultsView.as_view(), name="race-results"),
    path("racing/races/<int:race_id>/", RaceDetailView.as_view(), name="race-detail"),
    path("competitions/standings/", StandingsView.as_view(), name="standings"),
    path("riders/", RiderListView.as_view(), name="riders"),
    path("teams/claim/", ClaimTeamView.as_view(), name="claim-team"),
    path(
        "teams/spells/<int:spell_id>/acknowledge/",
        AcknowledgeSpellView.as_view(),
        name="acknowledge-spell",
    ),
    path("staff/", StaffView.as_view(), name="staff"),
    path("staff/trainer/hire/", HireTrainerView.as_view(), name="hire-trainer"),
    path("staff/trainer/fire/", FireTrainerView.as_view(), name="fire-trainer"),
    path("staff/training/", TrainingView.as_view(), name="training"),
    path("economy/finances/", FinancesView.as_view(), name="finances"),
    path("economy/sponsors/", SponsorsView.as_view(), name="sponsors"),
    path("economy/sponsors/sign/", SignOfferView.as_view(), name="sign-offer"),
    path("transfers/free-agents/", FreeAgentsView.as_view(), name="free-agents"),
    path(
        "transfers/free-agents/sign/",
        SignFreeAgentView.as_view(),
        name="sign-free-agent",
    ),
    path("transfers/riders/release/", ReleaseRiderView.as_view(), name="release-rider"),
]
