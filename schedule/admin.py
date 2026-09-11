from django.contrib import admin

from .models import Season, SeasonTransition, Week


class ReadOnlyAdmin(admin.ModelAdmin):
    """Seasons, weeks and transitions are written only by `load_season` and
    the tick — never by hand. See schedule/README.md."""

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(Season)
class SeasonAdmin(ReadOnlyAdmin):
    list_display = ("number", "starts_at", "ends_at")


@admin.register(Week)
class WeekAdmin(ReadOnlyAdmin):
    list_display = ("season", "number", "starts_at", "ends_at")
    list_filter = ("season",)


@admin.register(SeasonTransition)
class SeasonTransitionAdmin(ReadOnlyAdmin):
    list_display = ("season", "kind", "occurred_at", "recorded_at")
    list_filter = ("kind",)
