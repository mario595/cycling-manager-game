from django.contrib import admin

from .models import Rider


@admin.register(Rider)
class RiderAdmin(admin.ModelAdmin):
    list_display = (
        "name", "team", "speciality", "age",
        "climb", "sprint", "flat", "resistance", "positioning",
    )
    list_filter = ("team", "speciality", "nationality")
    search_fields = ("name",)
    fieldsets = (
        (None, {"fields": ("name", "nationality", "team")}),
        ("Engine attributes", {
            "fields": ("climb", "sprint", "flat", "resistance", "positioning"),
        }),
        ("Visible, between-race", {
            "fields": ("speciality", "height_cm", "weight_kg", "age"),
        }),
        ("Hidden traits — inspectable, never shown to the player", {
            "classes": ("collapse",),
            "fields": (
                "potential", "peak_age", "decline_rate",
                "injury_proneness", "training_affinity",
            ),
        }),
    )
