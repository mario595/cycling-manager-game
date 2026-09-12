from django.contrib import admin

from .models import Race, RaceLog, RaceResult, RaceSquad, RaceSquadRider


@admin.register(Race)
class RaceAdmin(admin.ModelAdmin):
    list_display = ("name", "status", "starts_at", "week", "wind_enabled", "seed", "created_at")
    list_filter = ("status", "week")


@admin.register(RaceLog)
class RaceLogAdmin(admin.ModelAdmin):
    list_display = ("race", "tick_count", "size_bytes")


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
