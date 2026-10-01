from django.contrib import admin

from .models import (
    MarkerCrossing,
    Race,
    RaceLog,
    RaceMarker,
    RaceResult,
    RaceSquad,
    RaceSquadRider,
    StageRace,
)


class RaceMarkerInline(admin.TabularInline):
    model = RaceMarker
    extra = 0


@admin.register(Race)
class RaceAdmin(admin.ModelAdmin):
    list_display = (
        "name", "status", "starts_at", "week", "stage_race", "stage_number",
        "wind_enabled", "seed", "created_at",
    )
    list_filter = ("status", "week", "stage_race")
    inlines = [RaceMarkerInline]


class RaceInline(admin.TabularInline):
    model = Race
    extra = 0
    fields = ("stage_number", "name", "status", "starts_at")
    ordering = ["stage_number"]


@admin.register(StageRace)
class StageRaceAdmin(admin.ModelAdmin):
    list_display = ("name", "week", "created_at")
    list_filter = ("week",)
    inlines = [RaceInline]


@admin.register(RaceLog)
class RaceLogAdmin(admin.ModelAdmin):
    list_display = ("race", "sample_count", "tick_interval", "size_bytes")


@admin.register(RaceResult)
class RaceResultAdmin(admin.ModelAdmin):
    list_display = ("race", "position", "rider", "finish_time")
    list_filter = ("race",)


class RaceSquadRiderInline(admin.TabularInline):
    model = RaceSquadRider
    extra = 0


@admin.register(RaceSquad)
class RaceSquadAdmin(admin.ModelAdmin):
    # This admin can save a squad that isn't exactly four riders with
    # exactly one leader — `racing.services.set_squad` is the sanctioned
    # writer that enforces that rule. The admin exists for inspection, not
    # for play.
    list_display = ("race", "team", "is_auto_picked")
    list_filter = ("race", "is_auto_picked")
    inlines = [RaceSquadRiderInline]


@admin.register(MarkerCrossing)
class MarkerCrossingAdmin(admin.ModelAdmin):
    list_display = ("marker", "position", "rider", "crossed_at")
    list_filter = ("marker__race",)
