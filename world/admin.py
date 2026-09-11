from django.contrib import admin

from .models import GameClock, TickRun


@admin.register(GameClock)
class GameClockAdmin(admin.ModelAdmin):
    list_display = ("current", "catch_up_max_races")


@admin.register(TickRun)
class TickRunAdmin(admin.ModelAdmin):
    list_display = (
        "started_at", "races_started", "races_finished", "capped",
    )
    list_filter = ("capped",)
