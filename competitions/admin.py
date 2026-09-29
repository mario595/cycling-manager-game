from django.contrib import admin

from .models import MarkerPoints, RacePoints


@admin.register(RacePoints)
class RacePointsAdmin(admin.ModelAdmin):
    list_display = ("race", "team", "position", "points")
    list_filter = ("race",)


@admin.register(MarkerPoints)
class MarkerPointsAdmin(admin.ModelAdmin):
    list_display = ("marker", "team", "rider", "position", "points")
    list_filter = ("marker__race",)
