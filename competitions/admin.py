from django.contrib import admin

from .models import RacePoints


@admin.register(RacePoints)
class RacePointsAdmin(admin.ModelAdmin):
    list_display = ("race", "team", "position", "points")
    list_filter = ("race",)
