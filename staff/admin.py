from django.contrib import admin

from .models import Trainer


@admin.register(Trainer)
class TrainerAdmin(admin.ModelAdmin):
    list_display = (
        "name", "team", "speciality",
        "climb", "sprint", "flat", "resistance", "positioning",
    )
    list_filter = ("team", "nationality")
    search_fields = ("name",)
    readonly_fields = ("speciality",)
    fieldsets = (
        (None, {"fields": ("name", "nationality", "team")}),
        ("Skills", {
            "fields": (
                "climb", "sprint", "flat", "resistance", "positioning",
                "speciality",
            ),
        }),
    )
