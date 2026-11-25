# A claimed team keeps its riders

**Status:** implemented
**Domain(s):** `teams/`, `riders/`, `world/` (the measurement), `beta_agents/` (the players' guide), `frontend/` (claim wording)
**One-liner:** Taking over a team means taking over its squad, and new managers
are given the free team from the middle of the field, so joining late is no
longer a sentence to the bottom of the table.

Issue: [#156](https://github.com/mario595/cycling-manager/issues/156).
Supersedes one decision of `specs/archive/claiming-a-team.md` (see *Decisions
taken*).

## Why this exists

#156 started as an economy bug. Four of the five LLM tester teams on staging
were losing $6,000–$12,000 a week. Reading the staging ledgers showed that
the prices were not the cause. In season 3 the eleven AI teams had a median
result of about **+$65,000**, at or above the break-even target in
`economy/README.md`, *Balance targets*. The tester teams earned **$2,000–$10,000**
of prize money each in season 3, while the AI median was about $80,000. Their
results-linked sponsorship fell with their results.

They raced badly because of the claim. Claiming a team throws its riders into
the free-agent pool and hands the new manager a freshly generated roster at
day-one strength. In season 1 that is fair, because every team is at day-one
strength. By season 3 the AI teams have trained for three seasons. A fresh
roster's top four average about 204 strength, the weakest AI team's top four
are at 263, and the AI average is about 290. So a claimed team starts below
every team in the world. By design the bottom of the table loses money, so
the claimed team loses money. Every human who joins a real-time world after
its first season would meet the same thing. The claim also dumped about fifty
good riders aged 22–30 into the pool, where they went unsigned and the weekly
expiry retired them.

## Player experience

A player signs up and is told which team is now theirs. As before, they do not
pick it. It is a team from the middle of the field: not the champion and not
the team at the bottom, but one that has been scoring about as well as anyone.
They name it and give it a code, as before.

Then they meet their riders, and the riders are the squad that raced for the
team yesterday. They have the same names, the same strengths and weaknesses,
the same ages, and the same wage bill. The trainer is still there. If the last
manager left the squad short-handed, which a team lost to insolvency usually
is, the empty places are filled with newly generated riders, so the roster is
back to twelve.

The money and the following start fresh, as they always have. The balance is
the standard starting amount, the fanbase is reset, the previous owner's
sponsor deal and auction listings are gone, and the development squad is
closed. The new manager inherits a team that races about as well as an average
team, so it earns about what an average team earns. The economy is tuned for
exactly that team.

## In scope

1. A claimed team keeps every rider on its roster. No rider leaves the team
   because it changed hands.
2. When a player claims, they are given the unmanaged team whose squad
   strength is closest to the middle of the whole field (every team, managed
   or not), not the first free team in a fixed order.
3. If the claimed team has fewer than twelve riders, it is topped up to twelve
   with newly generated riders. A team with twelve or more is left as it is.
4. Everything else a claim does is unchanged: the new name and code, the
   standard starting balance, the fanbase reset, the previous sponsor deal
   voided, the team's open listings cancelled and live bids withdrawn, the
   development squad closed, the trainer kept, and the league position, points
   and history kept.
5. The economy measurement claims a team partway through a world and reports
   that team's next full season beside the AI average. A regression would then
   show up as a number, not as a beta tester's diary.
6. Every place that tells a player what claiming does says the team's squad
   comes with it: the claim screen, the players' guide that the LLM testers
   read, and the API's description of the claim.

## Out of scope

- **The pyramid** (#10, #11, #13, #14). It is the long-term answer to a wide
  spread between strong and weak teams, but on its own it would not have fixed
  this, because a fresh roster was weaker than every AI team. It stays where
  the roadmap has it. When it is built, #14 decides which division a new
  player lands in, and this feature decides what squad they find there.
- **A fresh roster scaled to the field.** This was considered and rejected; see
  *Decisions taken*.
- **Letting the player choose their team.** Placement is still assigned.
- **AI wage growth.** Strong AI teams' wage bills rise about 25% a season as
  their riders improve, but those teams still profit. It is not the drain.
- **Development squad costs.** These are optional spending, which the
  break-even target deliberately does not cover.
- **The missing season-4 sponsor**, which is #161.
- **Changing the claim cooldown's free release.** A rider the manager didn't
  choose can still be released for nothing during the cooldown, whether the
  rider was generated or inherited.

## Rules and edge cases

- **The middle of the field is about squad strength, not the table.** A team's
  league position this season is a mix of luck and timing. Its squad is what
  the new manager actually gets.
- **Who counts as the field.** Every active team in the world, including teams
  that humans manage. A world full of strong humans therefore hands out a
  stronger middle team.
- **Ties and the degenerate case.** When two free teams are equally close to
  the middle, either may be handed over, but always the same one for the same
  world. When only one free team is left, that one is handed over. When none
  is left, the player is told so, as today.
- **Top-up riders are new riders at day-one strength.** They fill places; they
  are not compensation. A stripped team is therefore weaker than an intact
  one, which is still better than today's outcome.
- **A roster above twelve is not trimmed.** Whatever the roster limit already
  allows, the claim leaves alone.
- **Inherited riders are unchanged.** An inherited rider keeps their
  salary, freshness, age, retirement warning and history. A rider due to
  retire at this season's close still retires.
- **Released-by-claim riders no longer exist as a category.** The free-agent
  pool is no longer topped up by claims. It now gets riders only from releases,
  unsold auctions, graduates and expiry, as already built.
- **The previous owner can be human.** A team lost to inactivity or insolvency
  is claimed with whatever roster it was left with, topped up if short.

## Decisions taken

- *Does the player inherit the team's riders?* **Yes.** This reverses the
  2026-09-11 decision in `specs/archive/claiming-a-team.md`. That decision
  rejected inheriting because "signup fairness would depend on how well the AI
  happened to trade". In practice the fresh roster turned out to be the
  unfair option once a world has aged: it put every late claimant below the
  whole field. The fairness concern is met by handing over the middle team
  instead. (Mario, 2026-11-25.)
- *Which free team does a claimant get?* The one closest to the middle of the
  field by squad strength. (Mario, 2026-11-25.)
- *What about a roster the last manager stripped?* It is topped up to twelve
  with generated riders. (Mario, 2026-11-25.)
- *Why not scale a fresh roster to the field instead?* It needs a calibration
  that someone has to keep in step with the world, and it adds code. Inheriting
  needs neither, because the world's own teams are already calibrated by
  definition. (Mario, 2026-11-25.)
- *Why not build the pyramid now?* It is four tickets and a re-tune, and a
  fresh roster would have been weakest in any division. See *Out of scope*.
  (Mario, 2026-11-25.)
- *Should the claim give more starting money?* No. Cash doesn't win races, and
  the starting balance stays as it is.
- *Is the economy re-tuned?* No. The AI field already meets the targets on
  staging. This feature puts new managers into that field rather than below it.

## Open questions

None.

## Deferred

- **Resetting the staging world after the merge**, so that the five testers
  re-claim teams under the new rule. It is an operation on staging, done once
  Mario says go, and it is not part of the build.
