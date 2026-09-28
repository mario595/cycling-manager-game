from __future__ import annotations

from django.urls import include, path

from .views import (
    AcknowledgeSpellView,
    AuctionMarketView,
    CalendarView,
    ClaimTeamView,
    ChangeDevelopmentSquadLevelView,
    ClockView,
    CloseDevelopmentSquadView,
    DevelopmentSquadView,
    FinancesView,
    FireTrainerView,
    FreeAgentsView,
    HireTrainerView,
    ListForAuctionView,
    LoginView,
    MeView,
    MyBidsView,
    OpenDevelopmentSquadView,
    PlaceBidView,
    PositionView,
    RaceDetailView,
    RaceLogView,
    RaceResultsView,
    ReleaseRiderView,
    RiderListView,
    RiderProfileView,
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
    path("racing/races/<int:race_id>/log/", RaceLogView.as_view(), name="race-log"),
    path("racing/races/<int:race_id>/", RaceDetailView.as_view(), name="race-detail"),
    path("competitions/standings/", StandingsView.as_view(), name="standings"),
    path("riders/", RiderListView.as_view(), name="riders"),
    path("riders/<int:rider_id>/", RiderProfileView.as_view(), name="rider-profile"),
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
    path(
        "development-squad/",
        DevelopmentSquadView.as_view(),
        name="development-squad",
    ),
    path(
        "development-squad/open/",
        OpenDevelopmentSquadView.as_view(),
        name="open-development-squad",
    ),
    path(
        "development-squad/level/",
        ChangeDevelopmentSquadLevelView.as_view(),
        name="change-development-squad-level",
    ),
    path(
        "development-squad/close/",
        CloseDevelopmentSquadView.as_view(),
        name="close-development-squad",
    ),
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
    path("transfers/auctions/", AuctionMarketView.as_view(), name="auction-market"),
    path("transfers/auctions/list/", ListForAuctionView.as_view(), name="list-for-auction"),
    path(
        "transfers/auctions/<int:auction_id>/bid/",
        PlaceBidView.as_view(),
        name="place-bid",
    ),
    path("transfers/auctions/mine/", MyBidsView.as_view(), name="my-bids"),
]
