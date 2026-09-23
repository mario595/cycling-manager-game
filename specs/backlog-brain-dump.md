# Backlog — brain dump session 2026-09-11

**45 items, tracked as GitHub issues #5–#70.** This file is the index and the
reasoning record; the issues are the tracker. Each item below is prefixed with
its issue number.

Raw capture from a spoken brain dump, sliced into work items. Each item is a
candidate GitHub issue. **None of these are specs** — they are scoped-enough
stubs to be turned into specs (`/product-spec`) one at a time.

Conventions:
- **Domain(s)** = the label(s). New domains flagged `NEW`.
- **Tech concerns** are parked, not decided.

---

## Naming decisions taken in this session

| Concept | Chosen name | Why |
|---|---|---|
| Competitive pyramid tier | **Division** | "League" is ambiguous — reads as both the whole competition and one tier. Division is unambiguously a tier. |
| Parallel section within a Division | **Group** | Kept from the dump. Short, neutral, no real-world baggage. |
| The pyramid as a whole | **Competition structure** / "the pyramid" | Only needs a name in UI copy. |
| Riders picked for a specific race | **Squad** | "Roster" is already the whole team's rider list; needs to stay distinct. |
| Youth/development squad | **Development squad** (informally "the academy") | "Dev team" collides with software meaning throughout the codebase and docs. |
| A rider's whole set of riders | **Roster** | Already used this way in `frontend/`. |

---

## A. Season & time

### [#5] A1. Season as a first-class entity
**Domains:** `schedule` NEW, `world` NEW
- A Season is a fixed-length period (12–16 weeks, TBD) during which races happen.
- Between Seasons there is a break (1–2 weeks, TBD) with no racing — the window
  where promotion/relegation, contracts, sponsorships and salary reviews resolve.
- Seasons are numbered/dated and everything else (results, points, finances)
  hangs off a Season.
- **Open:** exact length; break length; do Seasons map to real-world calendar
  dates or are they abstract?

### [#6] A2. Game clock with a controllable speed
**Domains:** `world` NEW
- Game time advances at real time in production: 1 game week = 1 real week.
- In development, time must be fast-forwardable — simulate months in minutes.
- Everything time-driven (races, training, wages, sponsor payments, transfers)
  reads the clock rather than `datetime.now()`.
- **Tech concern (parked):** singleton game-date; scheduled job vs. tick command;
  how a sped-up clock interacts with jobs that assume a week of wall-clock.

### [#7] A3. Race calendar: races placed on days within a Season
**Domains:** `schedule` NEW
- A Season holds a collection of races, each assigned to specific day(s).
- Mix per Season: 2–3 long stage races (scaled-down Grand Tours), several short
  stage races, a number of one-day races.
- Calendar is visible to players so they can plan.
- **Open:** can two races share a day? Does a team's Division determine which
  races it is entered into, or is entry chosen?

### [#8] A4. Admin season-configuration tool
**Domains:** `schedule` NEW, `world` NEW
- An admin builds the next Season ahead of time: which races, which days, which
  courses, which Divisions each race belongs to.
- Needs to be usable before the Season opens and locked once it starts.
- **Open:** Django admin vs. a purpose-built screen; are Seasons cloned from a
  template of the previous one?

### [#9] A5. Stage race as an entity
**Domains:** `racing`, `schedule` NEW
- A stage race is an ordered sequence of races run on consecutive days, with a
  general classification accumulating across them.
- One-day races are the degenerate case — decide whether they are the same model
  or a separate one.
- **Open:** scaled-down length for the Grand Tour equivalents (a week? 10 days?);
  rest days.

---

## B. Competition structure

### [#10] B1. Divisions and Groups
**Domains:** `competitions` NEW
- Division 1 has exactly 1 Group; Division 2 has 2 Groups; Division 3 has 4, etc.
  (doubling per tier).
- Launch with 2 Divisions; open more as users sign up.
- **Open:** teams per Group; what happens to a half-empty Group; are AI teams
  used as filler?

### [#11] B2. Opening a new Division as the playerbase grows
**Domains:** `competitions` NEW, `world` NEW
- When signups outgrow the current pyramid, a new bottom Division opens.
- Needs to happen between Seasons without invalidating standings.
- **Open:** automatic on a threshold or an admin action?

### [#12] B3. Standings table per Group
**Domains:** `competitions` NEW
- Points earned at races accumulate into a Group standings table over a Season.
- Visible to players throughout the Season.
- **Open:** tie-breaking rules.

### [#13] B4. Promotion and relegation between Seasons
**Domains:** `competitions` NEW
- Bottom N teams of each Group are relegated (except in the lowest Division).
- Top N teams are promoted (except in Division 1).
- Resolves during the between-Season break.
- **Open:** N; how a team promoted from one of several Groups is assigned to a
  specific Group in the tier above.

### [#14] B5. Mid-season signup placement
**Domains:** `competitions` NEW, `accounts`
- A user signing up mid-Season needs a team placed somewhere sensible — probably
  the bottom Division — possibly taking over an AI team.
- **Open:** new team from scratch vs. inheriting an AI team and its roster.

---

## C. Scoring & classifications

### [#15] C1. Points for race results
**Domains:** `competitions` NEW, `racing`
- Every race awards Division/Group points by finishing position.
- Stage races award points per stage *and* for the final general classification.
- **Open:** points tables; do bigger races award more? does Division affect it?

### [#70] C2a. Course markers — named points a race records crossings at
**Domains:** `race_engine`, `racing`
- A **marker** is a named point on a course at a chosen distance, authored with
  the course. A race records the first N riders across it, in order.
- Two kinds — **sprint** and **mountain** — identical in mechanism, differing in
  name and in what consumes them. A marker knows nothing about points.
- Each marker carries a **weight**: a summit finish outranks a small hill, a
  final sprint outranks an early one.
- **Placed, not derived** — this answers C3's original open question. Deriving
  climbs from gradient would hand scoring control to the terrain model, make
  every lump a scoring opportunity, and rescore old courses whenever that model
  changed. Same principle as the season file: race design is authored.
- **Tech (parked):** the engine has no event concept at all — it emits per-tick
  positions. The log format grows to carry events, and `racing/README.md` already
  wants it slimmed; do both at once. Courses are flat `{length, gradient}` lists
  authored inline by [#7]'s season file, so that format changes too. Crossing
  order needs resolving within a tick. Adds no rider attribute, so it should
  avoid the six-course rebalance — confirm.

### [#16] C2. Sprint points
**Domains:** `race_engine`, `racing`
- The first N riders across a sprint marker score, declining down the order,
  scaled by the marker's weight.
- **Open:** how many places and how much? Do sprint points feed Division points
  ([#15]) or money ([#19]), or stay separate? Is the finish line itself a sprint
  marker or a special case?

### [#17] C3. Mountain points
**Domains:** `race_engine`, `racing`
- The twin of C2: first N over a mountain marker score, scaled by weight.
- **Tracked separately from sprint points and never pooled.** The separation is
  the point — a sprinter and a climber should be able to have good seasons doing
  entirely different things.
- **Resolved:** climbs are authored with a weight, not derived from gradient (see
  C2a). Named categories (HC, 1st, 2nd, 3rd) may survive as a *presentation* of
  weight — familiar, and better than a bare number — but that is display, not
  scoring.
- **Open:** how many places? Traditionally fewer than a sprint.

### [#18] C4. Sprinters' and climbers' classifications
**Domains:** `competitions` NEW, `racing`
- A stage race accumulates sprint and mountain points across its stages into two
  standings, each with a visible leader *during* the race.
- **The winner of each earns extra points for their team at the end of the stage
  race**, over and above the individual crossings.
- **That bonus is the design point.** Without it a classification is arithmetic
  nobody rides for. With it, "we cannot win this race but we can win the
  mountains" becomes a plan made at squad selection, before stage 1.
- **Open:** how large a bonus — enough to build a squad around, not enough to
  outweigh the race itself? Money too ([#19])? Tie-breaking (it will come up).
  Do one-day races have classifications at all? Jerseys in the race player? Does
  an abandoning rider keep accumulated points — [#37] locks the squad after stage
  1, so abandons happen.

### [#19] C5. Prize money for race results
**Domains:** `economy` NEW, `racing`
- Races pay out money as well as points, by position, and probably for
  classifications too.
- **Open:** payout tables; per-stage vs. overall.

---

## D. Economy

### [#20] D1. Team finances ledger
**Domains:** `economy` NEW
- Every team has a balance built from an append-only ledger of income and
  expenditure, with a visible transaction history.
- Income: prizes, sponsors, transfers, merchandise. Outgoings: salaries,
  development squad, trainers, transfer fees.
- **Open:** what happens when a team goes broke — this needs its own item.

### [#22] D2. Sponsorship contracts
**Domains:** `economy` NEW
- **Depends on D4** — offer sizes are driven by fanbase.
- Companies offer sponsorship contracts, signed before the Season starts (or on
  mid-Season signup).
- Fixed one-Season term, fixed weekly payment known at signing.
- **Open:** how many sponsors per team; are offers tailored to the team's
  Division and recent results?

### [#23] D3. Sponsor renewal based on performance
**Domains:** `economy` NEW, `competitions` NEW
- **Depends on D4** — the re-offer is priced off fanbase, not off final position
  alone.
- At Season end, an existing sponsor re-offers at a higher or lower amount,
  priced off the team's fanbase (which itself tracks results).
- **Open:** can a sponsor walk away entirely? Can a team be poached by a better
  sponsor after a strong Season?

### [#21] D4. Fanbase and merchandise revenue
**Domains:** `economy` NEW
- Each team has a **fanbase** — a slow-moving number that grows with good results
  and decays with bad ones.
- Merchandise pays out weekly as a function of fanbase, not of this week's
  results. No player decision; the decision-making version is deferred (see D4a).
- **Why a fanbase and not a direct formula:** prize money is instant and
  sponsorship is fixed for a Season. Deriving merchandise straight from recent
  results would make it a third copy of "win more, earn more". Routing it through
  a slow stock gives the economy a *lagging* income stream instead.
- Deliberate consequence: a newly promoted team is still earning on last Season's
  small fanbase, and a relegated team coasts on a big one for a few weeks while
  its wage bill has already become unsustainable. That trap is intended.
- **Decision taken:** fanbase is **visible** to the player. Unlike hidden rider
  potential there is no interesting inference to make — the player already knows
  whether they have been winning — so hiding it would be opacity without payoff.
- **Decision taken:** fanbase **also drives sponsor offer sizes** (D2/D3). It is
  the single prestige number the whole economy reads from, rather than sponsors
  reading Division position directly. This makes fanbase load-bearing: build it
  before D2/D3 are specced.
- **Open:** growth/decay rates; does fanbase have a floor or ceiling per Division?

### [#24] D4a. Merchandising as an investment *(deferred)*
**Domains:** `economy` NEW
- Later option: let the player spend to convert fanbase into revenue more
  efficiently — a kit supplier, a shop, a merchandising deal — possibly trading
  short-term cash against long-term fanbase.
- **Deferred:** it is a decision about a spreadsheet rather than about bike
  racing, and it is the wrong place to spend design effort before the transfer
  market exists.

### [#25] D5. Rider salaries paid weekly
**Domains:** `economy` NEW, `riders`
- Each rider has a known weekly salary, debited every game week.
- **Open:** where the initial salary comes from — derived from attributes?

### [#26] D6. Post-Season salary renegotiation
**Domains:** `economy` NEW, `riders`
- After each Season a rider's salary may rise based on how much they improved.
- The player then chooses: keep them at the new salary, or sell.
- **Open:** can a rider refuse and leave? Is there a contract length at all, or
  is it a rolling weekly deal?

### [#27] D7. Insolvency: the escalation ladder
**Domains:** `economy` NEW
- **Not raised in the dump — flagged as a gap.** Open questions answered 2026-09-15.
- **Insolvent is a state, not a punishment:** cannot pay this week's wage bill.
  Visible, warned, and **survivable if the manager acts** — if it is not, the
  middle rungs are theatre and the game may as well take the team at once.
- **The ladder:** week 1 warning + transfer embargo → weeks 2–3 forced sales →
  week 4+ team lost, via [#62].
- **Transfer embargo** blocks *acquiring* — no buying, no free agents, no staff.
  Goes first because it is preventive and costs nothing already held, and because
  forced sales alone are gameable (sell, respend, insolvent again next week).
- **Forced sales — the listing is the commitment.** The manager is told how much
  weekly wage to shed and picks who to list. Listed riders leave **whether or not
  they sell**: a buyer means money, no buyer means a free agent and nothing. The
  wage stops either way. Collapses sell-and-release into one rule with no thin-
  market fallback — an unsold rider is a sale at zero — and makes listing risky,
  since a rider cannot be pulled back when the rescue bid does not come.
- **Rejected:** points deductions (punishes sport for finance, compounds the
  problem, collides with [#46] preserving points); instant loss on a negative
  balance (illegible — a team can look fine a week from disaster); AI takeover
  while the manager watches ([#44] already covers unmanaged teams).
- **Genuinely deferred, not merely unscheduled:** it has nothing to operate on.
  Needs wages ([#25]), a market ([#28]/[#29]) and a ledger ([#20]).

## E. Transfers & squad building

### [#28] E1. Transfer market with rider auctions
**Domains:** `transfers` NEW, `economy` NEW
- Teams list riders for sale; other teams bid; auctions resolve on a deadline.
- **Open:** auction duration; sniping protection; minimum price; does a rider get
  a say?

### [#29] E2. Free agents
**Domains:** `transfers` NEW
- Riders without a team exist (the model already allows it). Define how a team
  acquires one and what it costs.
- **Open:** how riders become free agents — released, unsold, retired-from-academy?

### [#30] E3. AI teams participating in the market
**Domains:** `transfers` NEW, `world` NEW
- Since most teams are AI-controlled, they must buy, sell and bid, or the market
  is dead at launch.
- **Open:** how aggressive; does AI bidding set a price floor?

### [#31] E4. Rider market value
**Domains:** `transfers` NEW
- A visible or inferable valuation to anchor bidding.
- Explicitly deferred out of `specs/archive/rider-attributes.md` as an output of the
  market rather than an attribute.

---

## F. Development squad

### [#32] F1. Development squad as a facility
**Domains:** `riders`, `economy` NEW, `teams`
- A team may run a development squad at a recurring weekly cost.
- Not recommended for new managers — it is an investment, not a starting asset.
- **Open:** is it a binary on/off, or does it have levels that change intake
  quality/volume?

### [#33] F2. Youth intake generation
**Domains:** `riders`
- On a fixed cadence (weekly, TBD), new young riders spawn into the development
  squad.
- Intake varies wildly in quality: some are hopeless regardless of training,
  some are promising but currently far below professional level.
- Builds directly on hidden `potential` from `specs/archive/rider-attributes.md`.
- **Open:** how many per cycle; does the cost/level of the squad bias quality?

### [#34] F3. Promote, retain or discard youth riders
**Domains:** `riders`, `teams`
- The player triages intake: promote to the senior roster, keep in the squad to
  train longer, or discard.
- The decision is interesting only because potential is hidden — this is the
  payoff of the hidden-attribute design.
- **Open:** is there a cap on squad size? Do discarded riders enter the free
  agent pool or vanish?

---

## G. Training

### [#35] G1. Trainers as hireable staff
**Domains:** `staff` NEW, `economy` NEW
- Trainers are hired from a pool (not auctioned): an upfront fee plus a monthly
  salary.
- Each trainer has a per-skill score; higher score means faster rider progress in
  that skill.
- **Open:** one trainer per team or several? How the pool refreshes. Can a
  trainer be poached or fired?

### [#36] G2. Weekly training focus
**Domains:** `riders`, `staff` NEW
- Each week the player picks one skill for the trainer to focus on.
- Riders gain mostly in that skill, marginally in others.
- Interacts with hidden potential, age curve and training affinity from
  `specs/archive/rider-attributes.md`.
- **Open:** is the focus team-wide or per-rider? Does training cost freshness?

---

## H. Race participation

### [#37] H1. Squad selection for a race
**Domains:** `racing`, `teams`
- Before a race the player commits a squad of N riders.
- For stage races the squad is locked after stage 1 — injuries and abandons
  cannot be replaced.
- **Open:** squad size (real life is 8; likely scaled down); penalty for failing
  to enter a squad in time.

### [#38] H2. Per-race team tactics
**Domains:** `racing`, `race_engine`
- Before each stage or one-day race the player sets a team tactic.
- **Open — the big one:** what a tactic actually *is*. Candidates: nominating a
  protected leader, aggression level, when to attack, whether to chase, sprint
  train commitment, energy budgeting. Needs a spec of its own before anything
  else here proceeds.
- **Tech concern (parked):** the engine currently takes leader/support roles
  only; richer tactics mean new engine inputs and re-verifying course balance.

### [#39] H3. Auto-entry and default behaviour for absent managers
**Domains:** `racing`, `world` NEW
- A player who doesn't log in still needs a squad and a tactic, or their team
  fails to start.
- **Open:** last-used squad, best-available auto-pick, or a DNS?
- *Not mentioned in the dump — flagged as a gap, since the game runs in real time
  and players will miss races.*

---

## I. Accepted additions

*(I1 "team facilities" was proposed and **cut**.)*

### [#40] I2. Staff roles beyond the trainer
**Domains:** `staff` NEW, `economy` NEW
- **Principle:** a staff role earns its existence only if it makes a decision the
  player could not otherwise make. A hire that is a flat +X% to something is a
  money sink wearing a costume, not a role.
- Three roles for MVP, each selling a different currency:
  - **Trainer** — improvement. Already scoped as G1/G2.
  - **Physio** — availability. Speeds injury recovery, possibly reduces injury
    risk. Creates the real choice: rush a rider back for a Grand Tour, or heal.
    Depends on I3.
  - **Scout** — information. Narrows the visible range on hidden potential for
    youth intake and transfer targets. The strongest of the new roles, because
    `specs/archive/rider-attributes.md` is built entirely on hidden attributes: a scout
    turns F3 (promote/retain/discard) from a coin flip into a judgement.
- **Decision taken:** fixed slots — one of each role per team, not a stackable
  pool. Keeps each hire meaningful instead of turning staffing into a budget
  allocation puzzle.
- **Considered and cut:** *nutritionist* (a +X% on freshness recovery; fold into
  physio if wanted), *mechanic* (needs mechanical failures, which the engine does
  not model).
- **Deferred:** *directeur sportif*, affecting how faithfully a team executes its
  tactic. Blocked on H2 — quality-of-execution cannot be defined before a tactic
  is.
- **Open:** how the hiring pool refreshes; can staff be poached or fired; do staff
  have their own quality curve over time?

### [#41] I3. Injuries as a mechanic
**Domains:** `riders`, `racing`
- `specs/archive/rider-attributes.md` defines injury-proneness as an attribute and
  explicitly defers the mechanic itself.
- Riders can be injured in a race, be unavailable for a period, and recover.
- Gives H1 (squad locked after stage 1) its teeth, and gives the physio in I2
  something to do.
- **Open:** can riders be injured in training? Severity tiers? Is a rider ever
  lost permanently?

### [#42] I4. Rider retirement and roster churn
**Domains:** `riders`, `world` NEW
- Riders decline past their hidden peak and eventually retire.
- Without this, rosters ossify and both the development squad and the transfer
  market lose their reason to exist.
- **Open:** is retirement age-driven, attribute-driven, or a hidden trait of its
  own? Does the player get warning?

### [#43] I5. Season-end awards and world history
**Domains:** `competitions` NEW
- Persist per-Season records: Division and Group winners, classification winners,
  promotions and relegations, rider career histories.
- Cheap to build, and it is most of what makes a long-running world feel like it
  has a past.
- **Open:** how far back is history browsable; are there individual season awards
  (rider of the season) distinct from race results?

## J. Unmanaged teams *(added 2026-09-11, second session)*

A Division is full long before it has enough users: 16 teams, 6 users, 10
unmanaged teams. `teams.Team.manager` is nullable by design, so these already
exist in the model — nothing decides what they *do*.

Three questions hide in here, and conflating them is the trap:

1. **Do they race?** **Yes** — settled. Not really a choice: otherwise a 16-team
   Division has six teams worth of racing in it.
2. **Do they *decide*?** **Idle now, heuristic later** — settled. See J1 → J2.
3. **What does a new user inherit?** **The past, not the present** — settled.
   See J3.

### [#44] J1. Unmanaged teams: default squad selection
**Domains:** `world` NEW, `racing`, `teams`
- Unmanaged teams field a squad for every race, chosen by a cheap default rule.
- No training, no transfers, no sponsorship. That is J2.
- **Same problem as [#39]** — "a team with no human input needs a squad". One
  mechanism, not two.
- **Accepted limitation:** they are weak in a *predictable, unchanging* way. Human
  teams improve, these do not, so the gap widens every Season. Fine for a
  playtest, not for a league.

### [#45] J2. Unmanaged teams: simple heuristic AI
**Domains:** `world` NEW, `teams`, `transfers` NEW, `staff` NEW
- Squad by course suitability, rotating training focus, transfers within budget.
- **Expiry condition on J1, and the point of this item:** the first full Season
  played with real users. A Season ending with every human above every unmanaged
  team is not a competition, and it makes promotion/relegation ([#13])
  meaningless — teams move by headcount, not merit.
- **Ongoing cost, stated plainly:** every new player-facing system needs an AI
  branch or unmanaged teams fall behind in that dimension. Budget for it.
- **Alternative considered — scripted results:** generate their results toward a
  target rather than simulating decisions. Cheaper, never falls behind a new
  system, but makes racing against them fake in a way the race player would
  expose. Revisit if the AI branch cost gets out of hand.
- **Open:** how strong should they be? Matching the human average is the obvious
  target and probably wrong — it removes the reward for playing well.

### [#46] J3. What a new user inherits when claiming a team
**Domains:** `accounts`, `teams`, `competitions` NEW

**Decision taken 2026-09-11: inherit the past, reset the present.**

| Inherited | Reset |
|---|---|
| Classification position | Money — fixed starting amount, same for everyone |
| Points this Season | Riders — a standard starting roster |
| Identity: name, code, colours | Staff, sponsorships |
| Results history | |

- **The line is backward- vs. forward-looking.** Points and classification
  *describe what already happened* and change nothing about future capability.
  Riders and money *are* future capability. The new user steps into a story
  without stepping into an advantage.
- **Riders considered for inheritance and rejected.** A roster *is* economics —
  fixing the cash and varying the roster fixes the smaller half. It would couple
  signup fairness to #45's AI quality (whoever claims the team the AI bought well
  for wins a lottery), and it cannot be fixed by making the AI fairer: an AI
  trading to keep rosters equal is not playing the game. It would also make one
  decision serve two masters — "play this team well" and "leave a fair
  inheritance" pull against each other.
- **Accepted consequence:** a team can lie 3rd with a brand-new roster. Legible,
  temporary, self-correcting within a Season. Not a problem to design around.
- **Open — where do the old riders go?** They cannot vanish or the world's rider
  population shrinks on every signup. Free agent pool ([#29], cleaner, gives #29 a
  natural supply) or redistributed among remaining unmanaged teams. Undecided.
- **Open:** reset on claim mid-Season or at the break? What happens when a user
  abandons a team?
- Splits cleanly from [#14]: that decides *where* a new user lands, this decides
  *what they get*.

---

## K. Player accounts *(added 2026-09-12)*

Not in the original dump, and not noticed until asked for directly: **there is
no way for a player to exist.** `accounts.User` is a model and nothing else — no
registration, no login, no logout, no URLs, no views. Users are created with
`createsuperuser` or through Django admin.

It sat unnoticed because every item that needs it starts *after* signup. [#14]
and [#46] both begin at "a user signs up", an event the game cannot produce.
`api/README.md` already records the symptom: the project default is
`IsAuthenticated`, but with no login flow in the SPA, endpoints were given
`AllowAny` to work around it — a workaround with no ticket behind it.

### [#50] K1. Player accounts: register, log in, log out
**Domains:** `accounts`, `frontend`
- Register, log in, log out; the SPA knows who is logged in.
- Lets endpoints stop opting out of `IsAuthenticated`.
- **Settled 2026-09-12: registration *claims* an unmanaged team**, it does not
  create one. No team-creation form. This gives K1 a dependency it did not have
  when written — on [#44] (unmanaged teams exist) and [#46] (what a claim hands
  over) — and moved account work later in `specs/roadmap.md`.
- **Open:** flow shape (account then claim, or one signup?); can a user pick
  which team, or is it assigned ([#14])? What does a logged-in user with no team
  see? Username or email as identifier? Open registration or invite-only?
- **Tech concerns (parked):** sessions are already configured and the SPA is
  same-origin, so sessions are the path of least resistance — CSRF needs settling
  either way. Package (`django-allauth`, `dj-rest-auth`) vs. hand-rolled against
  `django.contrib.auth` is a tech-plan call, not a spec one.

### [#51] K2. Account self-service
**Domains:** `accounts`
- Password reset, change password, change email, delete account.
- **Split from K1 deliberately** so the blocking half ships first. None of this
  blocks a playtest, and password reset drags in **email delivery** — a
  deployment and cost decision, not a game one.
- **Open:** which email provider, and does a free tier cover it? What happens to
  a deleted user's team — presumably back to the unmanaged pool, which makes this
  depend on [#44]/[#46]. Is email verified at registration at all?

---

## L. Losing a team *(added 2026-09-15)*

A manager can stop managing. The team returns to the unmanaged pool and is
re-claimable. `specs/archive/claiming-a-team.md` deferred "what happens to an abandoned
team" explicitly, waiting for *anything in the game that can remove a manager
from a team* — this is that thing.

**Split three ways because the mechanism and its triggers have wildly different
dependencies.** The mechanism is buildable now; one trigger needs only a
timestamp; the other needs an entire economy.

### [#62] L1. Losing a team: the mechanism
**Domains:** `teams`, `accounts`, `world` NEW
- A team is taken from its manager and returned to the unmanaged pool,
  re-claimable through the normal [#46] path.
- **Buildable now** — depends only on [#46], and closes its deferred question.
- **Decided 2026-09-15:** re-claiming confers **no advantage and no penalty** over
  a first-time signup — assigned team, fresh roster, same starting position. The
  **account keeps a record** of teams previously managed, so losing a team is a
  setback with a story rather than an erasure. Consistent with [#46] deciding a
  team's past is worth inheriting.
- **Open:** what is on the record, and who sees it? Grace period before removal?

### [#63] L2. Losing a team: inactivity
**Domains:** `accounts`, `world` NEW
- A manager who has not accessed the game for a defined period loses the team.
- A Division has fixed places; an absent manager occupies one while [#44] races
  their team badly forever.
- **The easier trigger, and the one to build first:** needs a timestamp and the
  clock, both of which exist. No dependency on money or a market.
- **Open:** how long — a Season is the natural unit? Does *access* mean logging
  in or actually picking a squad? How is the warning delivered with [#51]
  deferred and no email?

### L3. Losing a team: bankruptcy
Not a separate item — it is the last rung of [#27]'s ladder. Recorded here so the
two triggers are findable together.

---

## New domains this dump requires

| Folder | Status | Justified by |
|---|---|---|
| `schedule/` | needed | A1, A3, A4, A5 |
| `competitions/` | needed | B1–B5, C1, C4, D3, I5 |
| `economy/` | needed | C5, D1–D7, E1, F1, G1 |
| `world/` | needed | A1, A2, A4, B2, E3, H3, I4 |
| `transfers/` | needed | E1–E4 |
| `staff/` | **NEW — not in the current index** | G1, G2, I2 |
