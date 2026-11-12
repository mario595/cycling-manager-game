from __future__ import annotations

import pytest
from django.conf import settings
from django.test import Client, override_settings
from django.utils import timezone

from accounts.models import User
from feedback.models import Report

CHANGELIST = "/admin/feedback/report/"

# The admin's templates reference its CSS through {% static %}, which the
# manifest storage refuses to resolve until collectstatic has run. Tests do
# not run collectstatic, so render pages against the plain storage instead.
pytestmark = pytest.mark.usefixtures("plain_static_storage")


@pytest.fixture
def plain_static_storage():
    storages = {
        **settings.STORAGES,
        "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
    }
    with override_settings(STORAGES=storages):
        yield


@pytest.fixture
def staff_client(db):
    admin_user = User.objects.create_superuser(email="admin@example.com", password="s0meth1ng-good")
    client = Client()
    client.force_login(admin_user)
    return client


@pytest.fixture
def reporter(db):
    return User.objects.create_user(email="agent@example.com", password="s0meth1ng-good")


def _report(author, **overrides):
    fields = {
        "author": author,
        "category": Report.Category.BUG,
        "text": "Wages look doubled.",
        "game_time": timezone.now(),
    }
    fields.update(overrides)
    return Report.objects.create(**fields)


def test_staff_see_reports_and_can_filter_by_status(staff_client, reporter):
    _report(reporter, text="still new")
    _report(reporter, text="already dealt with", status=Report.Status.TRIAGED)

    response = staff_client.get(CHANGELIST, {"status__exact": "new"})

    assert response.status_code == 200
    assert b"still new" in response.content
    assert b"already dealt with" not in response.content


def test_the_bulk_actions_set_the_outcome(staff_client, reporter):
    first = _report(reporter)
    second = _report(reporter)

    staff_client.post(CHANGELIST, {"action": "mark_triaged", "_selected_action": [first.pk]})
    staff_client.post(CHANGELIST, {"action": "mark_dismissed", "_selected_action": [second.pk]})

    first.refresh_from_db()
    second.refresh_from_db()
    assert first.status == Report.Status.TRIAGED
    assert second.status == Report.Status.DISMISSED


def test_staff_cannot_add_a_report_by_hand(staff_client):
    assert staff_client.get(CHANGELIST + "add/").status_code == 403


def test_triage_saves_the_outcome_link_and_note_but_not_the_text(staff_client, reporter):
    report = _report(reporter)

    response = staff_client.post(
        f"{CHANGELIST}{report.pk}/change/",
        {
            "status": "triaged",
            "github_issue_url": "https://github.com/mario595/cycling-manager/issues/999",
            "triage_note": "Same as the deficit reports.",
            "text": "rewritten by staff",
        },
    )

    assert response.status_code == 302
    report.refresh_from_db()
    assert report.status == Report.Status.TRIAGED
    assert report.github_issue_url.endswith("/issues/999")
    assert report.triage_note == "Same as the deficit reports."
    assert report.text == "Wages look doubled."


def test_staff_can_filter_by_reporter(staff_client, reporter):
    other = User.objects.create_user(email="other@example.com", password="s0meth1ng-good")
    _report(reporter, text="from the agent")
    _report(other, text="from someone else")

    response = staff_client.get(CHANGELIST, {"author__id__exact": reporter.pk})

    assert response.status_code == 200
    assert b"from the agent" in response.content
    assert b"from someone else" not in response.content
