# What a new user inherits when claiming a team

**Status:** implemented
**Domain(s):** `teams/`, `riders/`, `accounts/`
**One-liner:** A new player takes over an existing unmanaged team, keeps its
league position and history, names it their own, and starts with a fresh squad
of riders rather than the one the AI left behind.

## Why this exists

A Division is full long before it has enough players — sixteen teams, perhaps
six humans. New players therefore do not create a team, they take one over. That
raises a question with no obvious answer: the team they take over already has a
past, a position in the table, and a roster of riders. Which of that comes with
it?

Giving a player everything makes signup a lottery — claim the team the AI
happened to build well and you start ahead of someone who claimed a bad one.
Giving them nothing means the table resets around them and the world has no
continuity. The answer this feature commits to is **inherit the past, reset the
present**: a new player steps into a story, but not into an advantage.

## Player experience

A player finishes signing up and is told which team is now theirs — they did not
pick it. They are shown where it stands: its position in the table, the points
it has already scored, the races it has already ridden. That is their history
now. Nothing about it is hidden or apologised for.

They are then asked for two things: a name for the team, and a three-letter code
for it. This is the moment the team becomes theirs rather than something handed
down. They can call it anything; the code is the short label that will appear
beside their riders in races and in the classification table. Nothing is
rejected for being already in use — there is no list of taken names to guess
against.

Then they meet their riders. It is not the squad the team had yesterday — those
riders have left and are now without a team. In their place is a fresh roster of
twelve, generated for them: the same number of riders, and the same overall
strength, as every other player received on their first day, but not the same
riders. A handful are clearly worth building around; a handful are clearly not;
most sit in between. Someone else's twelve are shaped differently — stronger
here, weaker there — for the same total. What they do with that is the game.

The effect, on the first day, is a team sitting third in the table with a squad
that never rode any of those races. That reads oddly for a week or two, and then
it stops mattering — the table moves, and the results start being theirs. It is
obvious to anyone looking that the team changed hands, which is exactly what
happened.

## In scope

1. Claiming a team assigns an existing unmanaged team to the new player; the
   player does not choose which one.
2. The claimed team keeps its position in the table, the points it has scored
   this Season, and its results history. These carry over unchanged.
3. The player sets a new name for the team as part of claiming it.
4. The player sets a new three-letter code for the team as part of claiming it.
5. Names and codes are not checked against other teams — a player is never told
   their choice is taken.
6. The team's results history and standings entry show the new name and code
   from that moment on, including for races ridden before the claim.
7. Every rider the team had before the claim leaves it and becomes a free agent.
   No rider is destroyed.
8. The team receives a newly generated roster of twelve riders: the same total
   strength as every other newly claimed team's roster, composed of different
   individual riders — some clearly worth keeping, some clearly not, most in
   between — so no two claimed teams start with the same squad.
9. All of the above happens at the moment of claiming, whenever in the Season
   that falls. The player can enter the very next race.
10. If no unmanaged team is available to claim, the player is told so clearly
    rather than being handed a broken account.

## Out of scope

- **Resetting the team's money to a standard starting amount.** Decided, not
  built: the game has no money. See *Deferred*.
- **Inheriting the team's position and points.** Committed to in scope above as
  a rule, but there is no standings table in the game yet for it to apply to.
  The rule is recorded so that whoever builds standings inherits the decision
  rather than re-opening it.
- **Choosing which team to claim.** Placement is assigned — that is
  [#14](https://github.com/mario595/cycling-manager/issues/14)'s question, not
  this one. A preview the player cannot decline is decoration; one they can is
  team-shopping, a different feature.
- **Setting the team's colours.** The claimed team's jersey colours carry over.
  Changing them belongs to a team-settings screen. *Later.*
- **Disambiguating two teams in the same Group that chose the same code.**
  Codes are deliberately not unique; making them readable where they collide is
  its own feature —
  [#56](https://github.com/mario595/cycling-manager/issues/56). *Later.*
- **What happens when a player abandons a team.** The game cannot currently
  remove a player from a team — there is no account deletion and no inactivity
  rule. *Later.*
- **Where the free agents released by a claim eventually go.** They exist and
  are unattached; a market for them is
  [#29](https://github.com/mario595/cycling-manager/issues/29). *Belongs to that
  feature.*

## Rules and edge cases

- **The name and code are the player's, permanently.** Neither is ever changed
  by the game. If two teams in one Group pick the same code, that is tolerated
  here and resolved where it is displayed, not by altering what the player
  chose.
- **A code is a label, not an identity.** Two teams may share one. It needs only
  to be readable beside a rider in a race and in a classification table.
- **A code is three uppercase letters.** Nothing else is accepted. This matches
  how team codes already appear in races.
- **Renaming does not fork the team's history.** There is one team; it changed
  its name. Past results are shown under the current name, not the one in force
  when they were scored. Real teams rename constantly and nobody is confused by
  it.
- **Released riders keep everything except their team.** Their attributes and
  identity are untouched — they simply have no team. The world's rider
  population never shrinks because someone signed up.
- **A generated roster is twelve riders, equal in total strength across teams,
  uneven within the roster.** Two players starting on the same day have squads
  worth the same overall and built from different individuals — some clearly
  strong, some clearly weak, most in between. Equal total strength is the
  fairness guarantee; the internal spread is what makes the first squad
  selection an actual decision rather than the same decision everyone else is
  making.
- **A roster is generated fresh per claim, not drawn from a fixed pool.** Two
  players never receive the same rider.
- **The claim applies mid-Season without waiting.** The alternative — holding
  the reset until the Season break — would mean a new player either races with
  the AI's inherited roster, which is the exact advantage this feature exists to
  prevent, or cannot race at all.
- **A claimed team looks inconsistent for a while, and that is accepted.** High
  in the table with a brand-new squad is legible, temporary, and self-correcting
  within a Season. It is not a problem to design around.

## Decisions taken

- *Does the player inherit the team's riders?* No. A roster is future capability,
  and inheriting it would make signup fairness depend on how well the AI happened
  to trade. (Settled 2026-09-11 on the issue.)
- *Does the player inherit position, points and history?* Yes. These describe
  what already happened and confer no advantage. (Settled 2026-09-11.)
- *What happens to the riders the team had?* They become free agents. Preserves
  the world's rider population and gives the future free-agent market a natural
  supply.
- *Does the player inherit the team's name?* No — they choose a new one. Identity
  is neither backward- nor forward-looking; the original decision's
  past-versus-future line simply did not cover it. A name carries no competitive
  advantage, so fairness says nothing about it, while a manager who cannot name
  their team is renting it.
- *How does renaming interact with inherited history?* The team is one continuous
  entity that changed name; history is shown under the new name throughout.
- *Does the player choose the team's code?* Yes, as part of claiming.
- *Must codes be unique?* No. A code is a display label; the team's identity is
  not the code. Uniqueness is only needed where codes are read side by side — a
  classification table or a race — and that is a Group-sized scope, handled at
  display time.
- *Does a code collision change a stored code?* No. Disambiguation is applied
  when a clashing code is displayed. Writing a suffix back would go stale the
  moment a team changed Group, and race records are immutable — a suffix written
  into one would permanently record a collision that may no longer exist.
- *Is the player warned that their code is already in use?* No. Removing the
  uniqueness rule exists precisely so the player never has to guess what is free.
- *Does the player choose the team's colours?* Not now; they carry over.
- *Are all starting rosters identical?* No — twelve riders each, equal in total
  strength across teams, uneven within each roster (some strong, some weak,
  most in between).
- *How many riders in a starting roster?* Twelve.
- *Does the roster generator need `rider-attributes` (age, speciality,
  potential) to exist?* It did, and that landed —
  [#57](https://github.com/mario595/cycling-manager/issues/57), merged. Roster
  generation for this feature uses `riders.generation.generate_roster()`
  directly rather than building a second mechanism.
- *Is the reset applied immediately or at the Season break?* Immediately.
- *Does the player see the team before committing to it?* No. Placement is
  assigned, so a preview implies a choice that does not exist.
- *Does an inherited table position carry prize money already paid?* No. Prize
  money is forward-looking in the same way riders are — it is not carried over.
  (Moot today: there is no money in the game yet.)

## Open questions

None. Roster generation ([#57](https://github.com/mario595/cycling-manager/issues/57))
is built and merged: `riders.generation.generate_roster(size, team=...)`
already produces a squad-sized group with the deliberate quality spread this
spec calls for. The implementation plan for this feature should use it
directly rather than building a second generator.

## Deferred

- **Resetting money to a fixed starting amount, identical for every team.**
  Decided; waiting because the game has no money at all, and the roadmap defers
  the entire economy as a group. Recorded here so it is applied, not re-argued,
  when it is built.
- **Inheriting classification position and Season points.** Decided and in scope
  as a rule; waiting because there is no standings table yet.
- **Team code disambiguation within a Group.**
  [#56](https://github.com/mario595/cycling-manager/issues/56). Needed the first
  time two teams in one Group share a code, which cannot happen before Groups
  exist.
- **Letting a manager change the team's colours.** A team-settings feature;
  nothing about claiming requires it.
- **What happens to an abandoned team, and whether it is reset again on the next
  claim.** Waiting for anything in the game that can actually remove a manager
  from a team.
