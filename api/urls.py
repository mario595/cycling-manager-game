from __future__ import annotations

from django.urls import path

from .views import ClockView, PositionView

app_name = "api"

urlpatterns = [
    path("world/clock/", ClockView.as_view(), name="clock"),
    path("schedule/position/", PositionView.as_view(), name="position"),
]
