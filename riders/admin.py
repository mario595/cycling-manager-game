from django.contrib import admin

from .models import Rider


@admin.register(Rider)
class RiderAdmin(admin.ModelAdmin):
    list_display = ("name", "team", "role", "climb", "sprint", "flat", "resistance", "positioning")
    list_filter = ("team", "role")
    search_fields = ("name",)
