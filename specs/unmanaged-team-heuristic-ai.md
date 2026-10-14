# Unmanaged teams: simple heuristic AI

**Status:** approved
**Domain(s):** `world/`, `racing/`, `staff/`, `economy/`, `teams/`
**One-liner:** Teams nobody manages choose their squads by the course, hire a trainer, train, and sign a sponsor, so they stay solvent and competitive instead of decaying.

## Why this exists

Today an unmanaged team picks its four riders without looking at the course, has no trainer and therefore trains nothing, and never signs a sponsor. It still pays wages every week. Human teams improve and earn sponsorship while unmanaged ones drift down, and their money runs out. The market half of this work shipped with the AI market; what is left is the rest of a manager's week.

Without it, the first full Season with real players ends with every human team above every unmanaged team. That is not a competition, and it would make promotion and relegation meaningless. This feature is a prerequisite for that Season, and it sits on an economic clock as well as a competitive one.

## Player experience

A player races against unmanaged teams and notices little, which is the point. Those teams no longer field the same naive four every week: on a mountain stage a climber-heavy team sends its climbers, and on a flat course its sprinters and rouleurs. Over a season they get stronger as their riders train, at roughly the pace a casual manager would manage.

Their finances hold steady. At the start of each Season an unmanaged team signs the steady sponsor and hires a modest trainer if it can afford one. A team that cannot afford one stays unstaffed and tries again later. A careful human, who picks squads every week, chooses sponsors deliberately and hires better trainers, still beats them. A human who stops paying attention does not necessarily keep up.

When a manager is released for inactivity, their team keeps its trainer, training focus and sponsor, and the AI carries on from there. When a player claims a team, they inherit the trainer the AI hired and take the team's sponsorship slot as it stands. They are not left unstaffed in their first week.

## In scope

1. For every race, an unmanaged team's squad is chosen with the course in mind: riders suited to the course are preferred, and tired riders rank behind rested ones as today.
2. Humans who do not pick a squad keep the existing naive default; the smarter pick applies to unmanaged teams only.
3. At the start of each Season, an unmanaged team with no trainer hires the cheapest adequate trainer from the shared pool, if it can afford the hire fee. It never takes the best trainers, so humans keep first pick of quality.
4. An unmanaged team that cannot afford a trainer stays unstaffed and tries again later.
5. An unmanaged team with a trainer trains each week on a rotating focus, weighted toward the specialities its roster actually holds.
6. At the start of each Season, an unmanaged team signs the steady (low-variance) sponsor from its offer round.
7. A team released for inactivity keeps its trainer and sponsor, and the AI continues its training.
8. A claimed team keeps its AI-hired trainer. This is a deliberate exception to "staff is reset on claim" (#46). The sponsor is voided on claim as before.
9. On a seeded season, the average unmanaged team loses no more than about half of what it loses today (about $65,500 a season), measured the same way and recorded in the world README. This feature narrows the gap; it does not close it.
10. Unmanaged-team hires, training and sponsors appear only where the game already shows a rival's staff or sponsor. No new screens.

## Out of scope

- **Stronger play in higher Divisions.** Later: there are no Divisions yet (#10). Revisit with #10 or #13.
- **Scripted results.** The ticket rejected it as the default, and the decisions above commit to real decisions.
- **A hidden "house trainer".** No: it would be a free asset humans cannot get.
- **A strength target or dial.** No: strength comes only from the decisions above. A dial would be the scripted-results approach under another name.
- **Matching the human average.** No: it removes the reward for playing well.
- **Development squads for unmanaged teams.** Later: only if youth proves to matter for how strong AI teams are.
- **Smarter default for absent human managers.** No: picking squads should stay rewarded.
- **Fixing the economy-wide wage-to-income deficit.** Not this ticket: it changes human finances too. Needs its own issue.
- **Market participation.** Already shipped as the AI market (#30); this feature does not change it.

## Rules and edge cases

- The AI never looks at hidden attributes: squad choice and hiring use only what a human can see.
- A team with too few riders to field a squad is still skipped with a warning, as today.
- Hiring and sponsor signing happen once per Season per team; re-running the same step must not hire twice or sign a second sponsor.
- An unmanaged team never overspends: it hires only when its balance covers the hire fee and a cushion for upcoming wages and salaries. The exact cushion is a plan decision.
- Sponsorship income is what lets unmanaged teams carry a trainer's salary. Insolvency handling for unmanaged teams (#27) is **not** solved here; that ticket must still decide whether the ladder applies to them. This feature only ensures they have income.
- **The deficit is not an AI problem.** A seeded season 1 measured the average unmanaged team at about $14,300 a week in wages against about $8,800 a week in income (prizes and merchandise), a loss of about $5,500 a week, ending the season with about $434,000 rather than the "$330,000" the world docs state. A human team has the same wage and income structure. The steady sponsor (about +$4,200 a week at today's fanbase) and a trainer (about −$1,500 a week plus the hire fee) roughly net out to a smaller loss, not a profit. Closing the gap means rebalancing wages, prizes or sponsor sizes for every team, which is a separate ticket, not this one.
- Every new player-facing system needs an AI branch or unmanaged teams fall behind in that dimension. This is a standing cost of the game, handled by each new ticket.

## Decisions taken

- **How strong?** A sensible but passive manager: reasonable weekly choices, no long-term planning. An attentive human beats it.
- **Trainers.** They hire from the shared pool, cheapest adequate trainer they can afford, never the best.
- **Sponsor.** Always the steady profile.
- **Training focus.** Rotate through the specialities the roster holds, weighted by how many riders have each.
- **Smarter squad pick.** Unmanaged teams only; absent humans keep the naive default.
- **Claiming a team with an AI-hired trainer.** The trainer stays; the sponsor is voided as before.
- **Success check (2026-10-14).** Reworded from "not trending toward zero" to "loses no more than about half of today's loss", after a seeded season showed the economy runs a deficit for every average team. The economy-wide deficit is out of scope here.
- **Docs correction.** Unmanaged teams do earn prize money; the world README and the roadmap are corrected as part of this work.

## Open questions

- What "adequate" means for a trainer, and how large the affordability cushion is. Resolver: the technical plan.
- Whether the AI hires only at Season open or also mid-season when it later becomes affordable. Scope item 4 says it retries "later"; the cadence is a plan decision.

## Deferred

- **Division-dependent strength:** needs Divisions (#10).
- **Development squads for AI teams:** wait to see whether youth matters for AI strength.
- **AI branches for future systems:** handled per ticket as each system lands.
