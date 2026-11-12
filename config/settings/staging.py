"""Staging settings: the production game on an accelerated clock (#129).

Everything comes from `prod.py` — the same image, the same env-driven
credentials, the same security settings — with exactly two differences:

- **The clock.** `AcceleratedClock` runs game time at 24× real time, so one
  game day passes per real hour and a twelve-week season plays out in about
  3.5 real days. It is set here, never from the environment, so production
  cannot end up on it by accident (world/README.md, *Which clock runs where*).
  The tick still runs from cron — every 5 minutes here, hourly in production
  (`TICK_SCHEDULE`, deploy/). Leave `TICK_ADVANCE_BY` unset: this clock moves
  by itself, and advancing it as well would skip game time.
- **The world can be wiped** between beta runs, with `seed_world --reset`
  (world/README.md, *The wipe*). It is off in `prod.py`.

Selected with `DJANGO_SETTINGS_MODULE=config.settings.staging`.
"""

from __future__ import annotations

from .prod import *  # noqa: F403

GAME_CLOCK_CLASS = "world.clocks.AcceleratedClock"
GAME_CLOCK_SPEED = 24

ALLOW_WORLD_RESET = True
