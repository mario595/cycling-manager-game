"""Triage. Staff work through reports here: filter, read the context, set an
outcome, attach the GitHub issue it became, and keep a private note.

What the reporter wrote and the context captured with it are read-only —
they are a record of the moment it was sent. Staff cannot add a report by
hand either: one with typed-in context would be a fiction.
"""

from __future__ import annotations

from django.contrib import admin

from .models import Report

TRIAGE_FIELDS = ("status", "github_issue_url", "triage_note")


@admin.register(Report)
class ReportAdmin(admin.ModelAdmin):
    list_display = (
        "created_at",
        "category",
        "status",
        "author",
        "team_name",
        "season_number",
        "week_number",
        "short_text",
    )
    list_filter = ("status", "category", "team", "author")
    search_fields = ("text", "author__email", "team_name")
    list_select_related = ("author",)
    readonly_fields = (
        "author",
        "category",
        "text",
        "location",
        "team",
        "team_name",
        "season_number",
        "week_number",
        "game_time",
        "created_at",
    )
    fieldsets = (
        ("Report", {"fields": ("author", "category", "text", "location")}),
        (
            "Context",
            {"fields": ("team", "team_name", "season_number", "week_number", "game_time", "created_at")},
        ),
        ("Triage", {"fields": TRIAGE_FIELDS}),
    )
    actions = ("mark_triaged", "mark_dismissed")

    def has_add_permission(self, request) -> bool:
        return False

    @admin.display(description="Text")
    def short_text(self, report: Report) -> str:
        return report.text if len(report.text) <= 80 else report.text[:79] + "…"

    @admin.action(description="Mark selected reports triaged")
    def mark_triaged(self, request, queryset):
        queryset.update(status=Report.Status.TRIAGED)

    @admin.action(description="Mark selected reports dismissed")
    def mark_dismissed(self, request, queryset):
        queryset.update(status=Report.Status.DISMISSED)
