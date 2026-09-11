from django.contrib import admin

from .models import GameClock, TickRun


@admin.register(GameClock)
class GameClockAdmin(admin.ModelAdmin):
    list_display = ("current", "last_advanced_at", "catch_up_hours")


@admin.register(TickRun)
class TickRunAdmin(admin.ModelAdmin):
    list_display = (
        "started_at", "trigger", "from_game_time", "to_game_time",
        "races_started", "races_finished", "capped",
    )
    list_filter = ("trigger", "capped")
