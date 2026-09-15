from __future__ import annotations

import pytest
from django.core.exceptions import ValidationError

from teams.models import Team


def test_two_teams_may_share_a_code(db):
    Team.objects.create(name="Team Alpha", code="ARD")
    Team.objects.create(name="Team Beta", code="ARD")

    assert Team.objects.filter(code="ARD").count() == 2


@pytest.mark.parametrize("code", ["ard", "ARDE", "A1D"])
def test_code_must_be_three_uppercase_letters(db, code):
    team = Team(name="Team Gamma", code=code)
    with pytest.raises(ValidationError):
        team.full_clean()
