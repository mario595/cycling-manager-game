# Staff

## What this app owns

`Trainer` — the shared hiring pool and the one trainer slot a team may fill
from it. Hiring and firing (`services.hire_trainer`, `services.fire_trainer`),
generation (`generation.py`), and the season-boundary top-up
(`services.top_up_pool`). Not what a trainer *does* once hired — that is
[#36](https://github.com/mario595/cycling-manager/issues/36), weekly
training focus. Not a fee or a salary for the slot — that is
[#69](https://github.com/mario595/cycling-manager/issues/69), deferred until
the ledger (`economy/`) exists. Not the physio or scout roles the original
brief also names — both wait on their own dependencies
([#41](https://github.com/mario595/cycling-manager/issues/41) for physio,
transfers/youth intake for scout).

## The one-slot rule

`Trainer.team` is a nullable `OneToOneField` to `teams.Team`, not a
`ForeignKey` on `Team` pointing at a trainer. `team = None` means the
trainer is unemployed, in the shared pool; a non-null `team` means they
fill that team's single slot.

This is what makes "a team cannot have two trainers" a database constraint
rather than an application-level rule someone has to remember to check: a
second `Trainer` row with the same `team` raises `IntegrityError` on save,
enforced the same way a `OneToOneField` enforces any other one-to-one
relationship.

The alternative — a `trainer` FK on `Team` — was rejected: it would invert
the dependency graph (`staff -> teams`, not `teams -> staff`), and it would
need a migration on `teams/` for a field only `staff/` cares about.

## Stored 1-100, displayed 0-10

A trainer's five skills (`climb`, `sprint`, `flat`, `resistance`,
`positioning` — deliberately the same names as `riders.models.
ENGINE_ATTRIBUTES`, since a training focus (#36) maps onto one of them) are
stored 1-100 and shown to the player on the 0-10 scale, through
`riders.display.to_display_scale` — the same mapping, the same function,
riders already use. See `riders/README.md`, *Display scale*.

Storing 1-10 directly (matching the product spec's player-facing wording
literally) was considered and rejected: ten buckets collapse the difference
between "clear speciality" and "close second", and #36 needs to scale a
training effect off the trainer's exact score in the focused skill, not off
a number already rounded away.

## The pool is shared, and hiring is contended

Every unemployed trainer (`team__isnull=True`) is visible to every team —
`services.available_trainers()`. Because two managers can try to hire the
same trainer at the same moment, `services.hire_trainer` locks the
requested row with `select_for_update()` and **no** `skip_locked`, then
re-checks `trainer.team_id is None` **after** the lock is held:

```python
trainer = Trainer.objects.select_for_update().get(pk=trainer_id)
if trainer.team_id is not None:
    raise TrainerNotAvailable(...)
```

This is the one genuinely concurrent operation in the app, and the
re-check after the lock is the line the whole feature depends on: without
it, the loser of a simultaneous hire silently overwrites the winner's claim
instead of being told the trainer is gone.

**Do not copy `teams.services.claim_team`'s `skip_locked=True` here.**
`claim_team` wants *any* unmanaged team and is happy to skip a contended
row and try the next one. Hiring is the opposite: the manager asked for
*that* trainer, specifically — `skip_locked` would make a contended row
silently vanish from the query, and the caller would see "not available"
indistinguishable from a genuine mistake, rather than "someone just took
this one".

## Generation guarantees the speciality

`generation.py` draws one skill (the speciality) from a high band (70-95)
and the other four from a lower, **non-overlapping** band (25-64). Because
the bands do not overlap, "exactly one skill is the clear highest" is true
by construction — there is no tie to break and no rejection loop. The
6-point gap between the bands' edges is chosen to survive the display
scale too: `floor(70/10)=7` against `floor(64/10)=6`, so the speciality
still reads as visibly taller on the bars a manager actually sees, not just
in the stored numbers.

The lower band's floor (25) exists for weekly training's benefit, not this
app's: #36 requires off-speciality training to always be worth something,
never zero, so no trainer skill is ever generated near the bottom of the
1-100 range.

## What `staff/` may import

`core`, `teams`, `riders` — matching `AGENTS.md`'s dependency graph. Never
`world/`, `api/`, `schedule/` or `racing/`. The season-boundary top-up is
wired the other way: `world.services.tick()` imports `staff.services.
top_up_pool` and calls it once per crossed `SeasonTransition`, using that
row's exactly-once guarantee for idempotency rather than anything tracked
in this app. See `world/README.md`, *How a tick works*.

## `seed_trainers` — the initial pool

```bash
python manage.py seed_trainers [--count=12] [--rng-seed=N]
```

Adds `--count` freshly generated trainers to the shared pool.
**Non-destructive** — unlike `riders/reset_riders`, it only adds and never
deletes, so it needs no `--yes`: there is no existing game content for it
to threaten. `--rng-seed` seeds the generator for a reproducible pool,
mainly useful for demos and manual testing.

## Future work / possible improvements

- **Fee and recurring salary** — [#69](https://github.com/mario595/cycling-manager/issues/69),
  once the ledger (`economy/`, [#20](https://github.com/mario595/cycling-manager/issues/20))
  exists. Hiring today is free.
- **Physio slot** — once [#41](https://github.com/mario595/cycling-manager/issues/41)
  (injuries) gives it something to affect.
- **Scout slot** — once transfers/youth intake give it something to narrow.
- **AI/unmanaged teams hiring a trainer** — belongs to
  [#45](https://github.com/mario595/cycling-manager/issues/45); unmanaged
  teams stay unstaffed for now.
- **Poaching, contract renewal, a trainer quality curve over time** — no
  current plan; a trainer's five scores are fixed for life, and the only
  way to change teams is to be fired back into the pool first.
