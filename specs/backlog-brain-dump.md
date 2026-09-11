# Backlog — brain dump session 2026-09-11

**All 36 items are now GitHub issues #5–#43.** This file is the index and the
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

### [#16] C2. Intermediate sprints and sprint points
**Domains:** `race_engine`, `racing`
- Each race/stage has sprint points at defined locations on the course; the
  first riders across score.
- **Open:** how many riders score, how many points; engine must record who
  crossed a given distance first.
- **Tech concern (parked):** the engine must emit crossing events at arbitrary
  course positions — likely new log event types.

### [#17] C3. Categorised climbs and mountain points
**Domains:** `race_engine`, `racing`
- Climbs are classified by difficulty (HC, 1st, 2nd, 3rd category).
- Points awarded at the summit, scaled by category.
- **Open:** does the classification derive automatically from gradient/length, or
  is it authored per course?

### [#18] C4. Secondary classifications (mountains and points jerseys)
**Domains:** `competitions` NEW, `racing`
- Stage races carry a mountains classification and a points classification
  alongside the GC, each with a leader.
- **Open:** do these award Division points, money, or only prestige? Are jerseys
  shown in the race player?

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

### [#27] D7. Insolvency rules
**Domains:** `economy` NEW
- Define what happens to a team that cannot pay its wage bill.
- **Open:** forced sales, transfer embargo, points deduction, AI takeover?
- *Not mentioned in the dump — flagged as a gap, since every other economy item
  assumes money can run out.*

---

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
- Explicitly deferred out of `specs/rider-attributes.md` as an output of the
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
- Builds directly on hidden `potential` from `specs/rider-attributes.md`.
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
  `specs/rider-attributes.md`.
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
    `specs/rider-attributes.md` is built entirely on hidden attributes: a scout
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
- `specs/rider-attributes.md` defines injury-proneness as an attribute and
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

## New domains this dump requires

| Folder | Status | Justified by |
|---|---|---|
| `schedule/` | needed | A1, A3, A4, A5 |
| `competitions/` | needed | B1–B5, C1, C4, D3, I5 |
| `economy/` | needed | C5, D1–D7, E1, F1, G1 |
| `world/` | needed | A1, A2, A4, B2, E3, H3, I4 |
| `transfers/` | needed | E1–E4 |
| `staff/` | **NEW — not in the current index** | G1, G2, I2 |
