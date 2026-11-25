from __future__ import annotations

from django.urls import include, path, re_path
from drf_spectacular.views import SpectacularAPIView, SpectacularRedocView
from rest_framework.exceptions import NotFound
from rest_framework.permissions import AllowAny
from rest_framework.views import APIView

from .views import (
    AcknowledgeSpellView,
    AuctionMarketView,
    CalendarView,
    ClaimTeamView,
    ChangeDevelopmentSquadLevelView,
    ClockView,
    CloseDevelopmentSquadView,
    DevelopmentSquadView,
    DiscardSquadRiderView,
    FinancesView,
    FireTrainerView,
    ForceSellView,
    FreeAgentsView,
    HireTrainerView,
    ListForAuctionView,
    LoginView,
    MeView,
    MyBidsView,
    OpenDevelopmentSquadView,
    PlaceBidView,
    PositionView,
    PromoteSquadRiderView,
    RaceDetailView,
    RaceLogView,
    RaceResultsView,
    ReleaseRiderView,
    ReportsView,
    RiderListView,
    DeparturesView,
    RiderProfileView,
    SignFreeAgentView,
    SignOfferView,
    SolvencyView,
    SponsorsView,
    SquadView,
    StaffView,
    StandingsView,
    TrainingView,
)

app_name = "api"


class ApiNotFoundView(APIView):
    """Every /api/ path that matches nothing above, for every method.

    Without it the SPA's catch-all in config/urls.py answers with index.html
    and a 200, which tells an API client nothing, and a missing trailing
    slash would land there too (#130; api/README.md, Browser assumptions).
    A DRF view, not a plain Django one: `APIView.as_view()` is what exempts it
    from CsrfViewMiddleware, so a write to an unknown path also gets this JSON
    404 rather than Django's HTML "CSRF verification failed" page. No
    authentication, so the answer is the same whoever asks.
    """

    authentication_classes: list = []
    permission_classes = [AllowAny]
    schema = None  # not an endpoint; keep it out of the OpenAPI schema

    def initial(self, request, *args, **kwargs):
        super().initial(request, *args, **kwargs)
        raise NotFound("No such API endpoint. API paths end with a slash.")

    # Every method resolves to a handler, so none is refused as 405 before
    # initial() raises the 404.
    def get(self, request, *args, **kwargs):  # pragma: no cover — initial() raises first
        raise NotFound()

    post = put = patch = delete = head = options = get


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
    path("riders/departures/", DeparturesView.as_view(), name="departures"),
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
    path(
        "development-squad/riders/<int:rider_id>/promote/",
        PromoteSquadRiderView.as_view(),
        name="promote-squad-rider",
    ),
    path(
        "development-squad/riders/<int:rider_id>/discard/",
        DiscardSquadRiderView.as_view(),
        name="discard-squad-rider",
    ),
    path("economy/finances/", FinancesView.as_view(), name="finances"),
    path("economy/solvency/", SolvencyView.as_view(), name="solvency"),
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
    path("transfers/auctions/force/", ForceSellView.as_view(), name="force-sell"),
    path(
        "transfers/auctions/<int:auction_id>/bid/",
        PlaceBidView.as_view(),
        name="place-bid",
    ),
    path("transfers/auctions/mine/", MyBidsView.as_view(), name="my-bids"),
    path("feedback/reports/", ReportsView.as_view(), name="reports"),
    # OpenAPI schema and its docs page, for authenticated users only
    # (SPECTACULAR_SETTINGS["SERVE_PERMISSIONS"]).
    path("schema/", SpectacularAPIView.as_view(), name="schema"),
    path("docs/", SpectacularRedocView.as_view(url_name="api:schema"), name="docs"),
    # Must stay last.
    re_path(r"^.*$", ApiNotFoundView.as_view()),
]
