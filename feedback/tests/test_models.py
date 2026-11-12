from __future__ import annotations

from datetime import timedelta

from django.utils import timezone

from accounts.models import User
from feedback.models import Report
from teams.models import Team


def _report(author, **overrides):
    fields = {
        "author": author,
        "category": Report.Category.BUG,
        "text": "Wages look doubled.",
        "game_time": timezone.now(),
    }
    fields.update(overrides)
    return Report.objects.create(**fields)


def test_a_new_report_starts_untriaged(db):
    author = User.objects.create_user(email="r@example.com", password="s0meth1ng-good")
    report = _report(author)

    assert report.status == Report.Status.NEW
    assert report.github_issue_url == ""
    assert report.triage_note == ""


def test_reports_list_newest_first(db):
    author = User.objects.create_user(email="r@example.com", password="s0meth1ng-good")
    older = _report(author)
    newer = _report(author)
    Report.objects.filter(pk=older.pk).update(created_at=timezone.now() - timedelta(hours=1))

    assert list(Report.objects.all()) == [newer, older]


def test_deleting_the_team_keeps_the_report_and_its_team_name(db):
    author = User.objects.create_user(email="r@example.com", password="s0meth1ng-good")
    team = Team.objects.create(name="Gone Team", code="GON")
    report = _report(author, team=team, team_name=team.name)

    team.delete()
    report.refresh_from_db()

    assert report.team is None
    assert report.team_name == "Gone Team"


def test_deleting_the_author_deletes_their_reports(db):
    author = User.objects.create_user(email="r@example.com", password="s0meth1ng-good")
    _report(author)

    author.delete()

    assert Report.objects.count() == 0
