# Weekly training focus

**Status:** proposed
**Domain(s):** `riders/`, `staff/` (new)
**One-liner:** Each week the manager picks one skill for the team's trainer to
focus on, and on Monday every eligible rider's attributes shift toward that
week's training and racing.

## Why this exists

Rider attributes exist and are visible, but nothing moves them yet — a rider
generated today has the same climb, sprint, flat, resistance and positioning
forever. Weekly training is the first thing a manager does regularly that
changes who their riders *are*, not just who they field. It also gives the
hidden `training_affinity` trait (already stored on every rider, currently
inert) its first live consequence: two riders who look identical on the
roster page can respond differently to the same training week, which is the
whole point of a hidden trait existing at all.

It turns the trainer, once hireable, into an ongoing weekly decision rather
than a one-time purchase — a team's shape a season from now depends on twelve
small choices made one Monday at a time, not just on who was hired in week 1.

## Player experience

Monday morning, the manager opens the team's Training page. A panel at the
top shows what happened from last week's training: a short list of riders
whose skill visibly moved, old value to new (e.g. "Rider X — climb 7 → 8"),
nothing shown for riders whose numbers didn't move enough to register on the
0-10 scale. Below it, if the team has a trainer, a picker lets the manager
choose one of the five skills as this week's focus — defaulting to whatever
was picked last week, so a manager who agrees with themselves just leaves it
alone. If the team has no trainer, there's no picker: the page just shows the
last-week summary and a prompt that hiring a trainer unlocks focused
training.

Whatever is selected by the moment the game week rolls over to Monday
00:00:00 UTC is what trains that week. Every eligible rider on the roster
moves a little on the focus skill, and a little more if their hidden
training affinity favours it — invisible to the player, so two riders can
respond differently to an identical week with no explanation offered, the
same as any other hidden trait in the game. Riders who raced during the week
also pick up a small nudge toward whatever skill the terrain they raced on
rewards, regardless of what the trainer was focused on, and regardless of
whether the team has a trainer at all. An injured rider sits the week out
entirely — no trainer effect, no race effect, because they didn't race and
didn't train.

None of this is dramatic week to week. Most Mondays, the roster page looks
the same. Over a season, the riders who got the right kind of racing and the
right training focus start to pull ahead of the ones who didn't.

## In scope

1. A team with a hired trainer can select exactly one skill (climb, sprint,
   flat, resistance, positioning) as that week's training focus.
2. The selection can be changed at any point before the week rolls over;
   only the value in effect at rollover (Monday 00:00:00 UTC) is used.
3. If the manager never changes it, the previous week's focus carries
   forward automatically — there is always a value in effect, never a gap
   week with no selection.
4. At rollover, every non-injured rider on the team's roster gets a
   training effect on the focus skill. The size of the effect is larger when
   the focus skill matches the trainer's speciality, smaller (but never
   zero) otherwise.
5. Riders respond to identical training differently depending on a hidden
   trait the player cannot see directly — only inferable from how much they
   improve.
6. Independently of the trainer, any rider who competed in at least one race
   that week gets a small attribute nudge toward the skill the terrain of
   that race favoured (e.g. a hilly race nudges climb). This happens whether
   or not the team has a trainer, and whether or not that skill was the
   trainer's focus.
7. A team with no trainer has no focus selector to interact with — training
   is not a decision they can make yet. Racing still produces its small
   independent effect on riders regardless.
8. An injured rider gets no effect from either the trainer or race
   participation that week.
9. The Training page shows, after each rollover, which riders had a
   skill move by a visible amount (on the 0-10 display scale) as a result of
   last week's training and racing, old value to new. Riders with no visible
   change are not listed.
10. Attributes can rise from training and racing; this feature never lowers
    an attribute.

## Out of scope

- **Per-rider training assignment.** One focus skill applies to the whole
  roster at once — the brief's "team can hire a trainer" (singular, fixed
  slot per #37) implies one trainer's attention isn't divisible across five
  different foci for five different riders. **No**, not planned — revisit
  only if a second trainer slot is ever introduced.
- **Training costing freshness.** Freshness doesn't exist yet (#59). **Later**
  — once #59 lands, spend a training-week freshness cost as a follow-up
  decision, not bundled into this feature.
- **Attribute decay for skills nobody trains.** An untrained, unraced skill
  never falls on its own. Attributes falling with age belongs entirely to
  #58 (rider growth and decline) — this feature is additive-only. **Belongs
  to #58.**
- **A dedicated training report/notification.** Folded into the same
  Training page as the focus picker (see In scope #9) rather than a separate
  screen. **No** separate surface planned.
- **Trainer hiring, wages, or the `staff/` app itself.** This spec assumes a
  trainer exists and describes what happens once a team has one; hiring one
  is #35's job entirely. **Depends on #35**, see Rules and edge cases.

## Rules and edge cases

- **No trainer means no focus decision, ever, not a temporarily-disabled
  one.** Until #35 ships trainer hiring, this entire feature's trainer half
  has nothing to attach to — see Decisions taken. Race-based training is the
  only effect a team can get today, and it already applies with no
  dependency on staffing.
- **A missed selection reuses last week's**, so there is no "did nothing"
  week purely from forgetting — a manager who never touches the picker keeps
  training the same skill indefinitely, which is itself a valid (if
  suboptimal) strategy.
- **Off-speciality training is always worth something.** A trainer whose
  speciality is climb still improves sprint when asked to, just less than a
  sprint-specialist trainer would. No selection is ever wasted outright.
- **Race-based training is separate from and additive to trainer-based
  training**, not a substitute for it — a rider who both raced a hilly
  course and had climb as the week's focus gets both effects, not the
  larger of the two.
- **Injury is a hard stop**, not a reduced effect — this defers entirely to
  whatever #41 (injuries) eventually defines as "injured"; this feature only
  needs to know the yes/no state.
- **The visible-change list is driven by the 0-10 display scale, not the
  underlying stored number** — a rider whose stored value moved from 71 to
  74 shows nothing, matching how growth (#58) is expected to surface and
  keeping training results from reading as a number that visibly creeps
  every week.
- **Multiple riders can appear in the same weekly list with different
  skills**, if a rider's race-based nudge landed on a different skill than
  the trainer's focus and both happened to cross a display-scale boundary
  the same week.

## Decisions taken

- Full trainer-driven feature specced now, even though #35 (trainer hiring)
  and the `staff/`/`economy/` apps it needs don't exist yet — build waits on
  #35, this spec doesn't. *(Scope vs roadmap)*
- No freshness cost — the field doesn't exist (#59 unbuilt); revisit once it
  does. *(Freshness cost)*
- Training focus is team-wide, one skill, not assignable per rider.
  *(Focus scope)*
- Race-based passive training always applies, trainer or not. *(Race-based
  training)*
- Weekly training results surface as a "what changed" list on the same page
  as the focus picker — old value → new value, only for riders whose
  display-scale number actually moved. *(Feedback)*
- Training never causes attributes to fall; only age-driven decline (#58)
  does that. *(Decay)*
- Off-speciality training always has some effect, never zero. *(Mismatch
  floor)*
- No trainer means no focus picker at all, not a picker that does nothing;
  race-based training is unaffected either way. *(No trainer)*

## Open questions

None outstanding — all of the ticket's open questions were resolved above.

## Deferred

- **Freshness cost for a training week** — once #59 (rider freshness) exists,
  revisit whether training should draw on it the way racing will.
- **A second trainer slot / per-rider training** — only worth reconsidering
  if the single fixed trainer slot (#37/#35) itself changes.
