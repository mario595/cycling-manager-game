from __future__ import annotations

from datetime import datetime


def touch_last_seen(user, at: datetime) -> None:
    """Stamp the user's game-time last-seen, called on login.

    `at` is passed in rather than read here so this stays a pure function of
    the caller's clock read — the same shape teams.services.claim_team and
    release_team take `at`, because accounts/ must not import world/ (see
    accounts/README.md, Last seen is game time).

    update_fields is deliberate: this runs on every login and must not write
    the rest of the row, which would race with anything else touching the
    user at the same time.
    """
    user.last_seen_at = at
    user.save(update_fields=["last_seen_at"])
