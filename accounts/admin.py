from django.contrib import admin
from django.contrib.auth.admin import UserAdmin

from .models import ApiToken, User

admin.site.register(User, UserAdmin)


@admin.register(ApiToken)
class ApiTokenAdmin(admin.ModelAdmin):
    """Read-only: a token is issued by `issue_api_token`, never typed in here,
    and only its hash is stored. Deleting a row revokes the token."""

    list_display = ("user", "prefix", "created_at")
    readonly_fields = ("user", "prefix", "created_at")
    exclude = ("key_hash",)

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False
