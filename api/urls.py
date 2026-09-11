from __future__ import annotations

from django.urls import path

from .views import ClockView

app_name = "api"

urlpatterns = [
    path("world/clock/", ClockView.as_view(), name="clock"),
]
