# Fanbase and merchandise revenue

**Status:** proposed
**Domain(s):** `economy`
**One-liner:** Every team has a fanbase that slowly rises on good results and falls otherwise, and pays out a weekly merchandise income based on how big it is.

## Why this exists

The ledger (#20) gave every team a balance and one outgoing — wages. Every
balance in the game currently only goes down. This ticket adds the first
income, and it deliberately isn't tied to this week's results the way prize
money (#19) will be: prize money is instant and sponsorship (#22/#23) is
fixed for a season, so deriving merchandise the same way would just be a
third copy of "win more, earn more." Routing it through a slow-moving
fanbase number instead gives the economy a genuinely different rhythm — an
income stream that lags behind form rather than tracking it.

That lag is the point. A team on a hot streak keeps earning modest
merchandise money for weeks after it started winning, because the fanbase
hasn't caught up yet. A team that just collapsed keeps coasting on a big
fanbase for a while too, even as its wage bill has become unsustainable.
Both are intended traps, not bugs to smooth away.

Fanbase is also the first "prestige" number the game has — a single figure
that says how big a team is, independent of where it sits in the standings
this week. Sponsor offers (#22/#23) will eventually price off it instead of
reading league position directly, which is why this ticket has to exist
before those can be specced.

## Player experience

On the Finances screen, next to the balance, a manager sees their team's
current fanbase and how it moved this week — up or down, with a rough
sense of scale, not just a raw count next to last week's raw count. A team
that just had a strong week sees fanbase tick up; a team on a losing run
sees it drift down, a little at a time, the same way the number moved for
everyone before they lost a race.

Every week, once the game clock crosses into a new week, two things happen
in order: the team's results from the week that just passed adjust its
fanbase, and its fanbase (as it now stands) pays out a merchandise income,
recorded on the Finances history as its own line — "Merchandise revenue,"
dated to that week, sitting alongside "Weekly wages" the same way any two
ledger entries do. The amount is never enough on its own to keep a team
afloat, but it's a real number, closing part of the gap the wage bill
opens every week.

A brand new manager who claims an unmanaged team inherits a fresh
start: fanbase resets to the standard starting figure the same moment
the balance does, regardless of how big or small the team's fanbase had
grown under nobody's management. Two managers who register on the same
day start exactly level, whether the team they picked had been quietly
winning or quietly losing beforehand.

If the clock is fast-forwarded through several weeks at once, the player
doesn't see one lump adjustment — they see the same one-change-then-payout
sequence play out once per week that was skipped, so the history reads as
a normal week-by-week story rather than a single mysterious jump.

## In scope

1. Every team — managed or unmanaged — has a fanbase: a number that moves
   over time and is never a matter of opinion, only of what happened.
2. Every team starts with the same fanbase, at the same moment it starts
   with the same balance.
3. Once each game week, a team's fanbase is adjusted based on the race
   results it produced that week: better results push it up, a week with
   nothing to show for it still costs a little.
4. Fanbase also drifts down slightly every week on its own, independent of
   results — a team has to actively perform to grow it, not merely avoid
   disaster.
5. Fanbase cannot fall below a small positive floor. A team on the worst
   possible run still has some fans left and can claw its way back.
6. Immediately after that week's fanbase adjustment, the team is paid a
   merchandise income based on its (now-updated) fanbase, recorded as its
   own dated entry in the team's financial history.
7. If the clock advances through more than one week at once, the
   adjust-then-pay sequence happens once per week that passed, each
   correctly dated — never a single combined change, never a skipped week.
8. A player can see their team's current fanbase and this week's change to
   it, alongside their balance.
9. Claiming an unmanaged team resets its fanbase to the standard starting
   figure, at the same moment and for the same reason its balance resets:
   every manager starts level, regardless of what the team's fanbase had
   become while unmanaged.

## Out of scope

- **Sponsor offers reading fanbase.** That's #22/#23's job once fanbase
  exists to read. This ticket does not describe a sponsor.
- **Any player decision about fanbase.** No spending it, no investing in
  it, no choices that affect how it grows. It is a pure consequence of
  racing, the same way the wage bill is a pure consequence of roster size.
  The decision-making version is [#24](https://github.com/mario595/cycling-manager/issues/24),
  deferred.
- **Other teams' fanbase.** A player sees their own team's number only.
  No league-wide fanbase ranking or comparison in this ticket.
- **A fanbase trend chart or history screen.** The weekly change shown
  alongside the current number is enough to answer "is this going up or
  down"; a graphed trend over a season is a later nicety.
- **Prize money, sponsorship, or any other income source.** Those are
  [#19](https://github.com/mario595/cycling-manager/issues/19) and
  [#22](https://github.com/mario595/cycling-manager/issues/22)/[#23](https://github.com/mario595/cycling-manager/issues/23),
  built on top of the same weekly ledger rhythm this ticket establishes,
  not folded into it.
- **A ceiling on fanbase.** Nothing to cap against with one Division and
  no promotion/relegation yet.
- **Fanbase varying between teams at world-seed time.** Every seeded team
  starts identical, same as the balance.

## Rules and edge cases

- **Fanbase moves once per week, not once per race.** A team racing twice
  in the same week doesn't get two fanbase adjustments; the week's results,
  however many races they came from, are read together when the week
  changes. This is what keeps fanbase a lagging signal rather than a
  per-race reaction — a podium doesn't visibly move it until the week
  turns over.
- **A team with no result to show for the week still loses ground.** The
  game has no notion of a "bad" finish separate from "no finish" — a team
  that raced and placed outside the scoring positions and a team that
  entered nobody look the same to the results data. Both are treated as a
  week with nothing to show for it: passive decay applies and nothing
  offsets it. This is a deliberate simplification, not an oversight — the
  alternative would require inventing a notion of a bad result the game
  doesn't otherwise have.
- **Passive decay applies to every team every week, including one that
  won.** A winning week is not "decay skipped" — it's a gain that outweighs
  the same decay everyone else pays. This is what keeps fanbase a genuine
  net-negative default rather than a number that only ever goes up.
- **The floor stops decay at a small positive minimum, never zero, never
  negative.** A team that has been losing for a long time keeps a small,
  stable base of support and a non-zero merchandise income — there is
  always a route back.
- **Merchandise income is meaningful but not sufficient.** It should read
  as a real number on the Finances history, comparable in scale to a
  fraction of the wage bill, but a team cannot rely on it alone to break
  even. Balancing it exactly is not this ticket's job to finish — that
  happens once prize money and sponsorship exist alongside it.
- **Fanbase is derived from a recorded history of weekly changes, never a
  single mutable number.** The same discipline the ledger already uses:
  each week's adjustment (from results and from decay) is its own dated
  row, and the current fanbase is the sum. This is what makes "why did my
  fanbase drop this week" answerable, and what keeps a fast-forwarded
  catch-up tick from silently landing on the wrong number.
- **A caught-up clock produces one adjust-and-pay cycle per week skipped,**
  each correctly dated to its own week — mirroring the wage bill's existing
  catch-up rule. A manager returning after time away sees exactly what
  happened, week by week, not one number that jumped.
- **Claiming a team resets fanbase to the standard starting figure,
  recorded as a new entry, never by erasing what came before.** The
  team's fanbase history from before the claim stays visible, the same
  way its financial history does — it just no longer contributes to the
  current number, because a new starting entry supersedes it. This is a
  deliberate fairness rule: two managers claiming teams on the same day
  must start level, regardless of how well or badly an unmanaged team
  had been doing.
- **Unmanaged teams accrue fanbase changes and merchandise income the same
  as managed ones.** No special case for a team with nobody behind it,
  matching how wages already work.

## Decisions taken

- **What makes fanbase fall: passive weekly decay, applied to every team
  every week.** The alternative — decay only on a week with no scoring
  result — was rejected because it can't be distinguished from a team
  that simply didn't race, and the game has no other notion of "bad."
  Passive decay sidesteps the question entirely: everyone bleeds a little
  by default, and only active winning outpaces it.
- **Fanbase is visible to the player**, per the originating issue — there
  is no interesting inference to protect by hiding it.
- **The player sees only their own team's fanbase**, not a league-wide
  comparison, keeping the MVP thin.
- **Fanbase is shown with its weekly change, not just a raw current
  number**, on the existing Finances screen — no new screen.
- **Every team starts at the same fanbase**, mirroring the ledger's
  opening-balance rule.
- **Claiming an unmanaged team resets its fanbase to the standard
  starting figure**, exactly as it resets the balance. Decided explicitly
  in this round: a newly registered manager must start level with every
  other newly registered manager, regardless of what an unmanaged team's
  fanbase had drifted to. This trades away part of the "inherit a big
  fanbase from a team that's been quietly winning" texture the original
  issue described, in favor of fairness between new managers — judged the
  right tradeoff today, since there's no promotion/relegation yet to give
  that inherited texture real meaning anyway.
- **Merchandise income is its own weekly ledger entry**, not folded into a
  combined income line, matching how "Weekly wages" already stands alone.
- **Merchandise income is meaningful but not sufficient** — enough to feel
  worth having, not enough to make a team solvent by itself.
- **Fanbase has a floor and no ceiling.** A floor keeps a failing team
  recoverable; a ceiling is a Division-tier concept that doesn't apply
  with one Division and no promotion/relegation.
- **Fanbase is derived from a recorded history of weekly changes**, not a
  single stored number — the same append-only discipline as the ledger,
  for the same reasons (auditable, catch-up-safe).
- **Fanbase moves once per week, off that week's combined results**, never
  per-race. This keeps it a lagging signal rather than a live reaction to
  each result.

## Open questions

None. The originating issue's two open questions are resolved above:
growth/decay happens through passive weekly decay offset by results
(*Rules and edge cases*), and fanbase has a floor but no ceiling
(*Decisions taken*).

## Deferred

- **Fanbase driving sponsor offer sizes** — [#22](https://github.com/mario595/cycling-manager/issues/22)/[#23](https://github.com/mario595/cycling-manager/issues/23),
  which read fanbase once it exists; this ticket only produces the number.
- **Merchandising as an investment** — [#24](https://github.com/mario595/cycling-manager/issues/24),
  already deferred in the backlog; no player decision touches fanbase here.
- **Fanbase on the league table or any cross-team comparison** — not
  useful with one Division and no promotion/relegation to give a
  comparison stakes.
- **A fanbase trend chart** — worth adding once there's more of a season's
  worth of history to look back on.
