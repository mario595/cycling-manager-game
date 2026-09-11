from __future__ import annotations

from django.urls import path

from .views import CalendarView, ClockView, PositionView

app_name = "api"

urlpatterns = [
    path("world/clock/", ClockView.as_view(), name="clock"),
    path("schedule/position/", PositionView.as_view(), name="position"),
    path("schedule/calendar/", CalendarView.as_view(), name="calendar"),
]
