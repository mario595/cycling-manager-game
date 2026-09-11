from django.contrib import admin

from .models import Race, RaceLog, RaceResult


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
