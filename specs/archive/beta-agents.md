# LLM beta testers

**Status:** implemented
**Domain(s):** a new top-level `beta_agents/` folder (not a Django app), with a deploy note in `deploy/`
**Issue:** #132
**One-liner:** five AI managers play the staging world on a schedule, each with its own team and play style, and report anything in the game that looks wrong.

## Why this exists

The staging world (#129) runs a season in about three and a half real days so
that season closes, salary reviews, retirements, youth intakes and insolvency
strikes happen often enough to be tested. Nobody can sit and play through that
by hand, and the first human testers should not be the ones who find the
obvious bugs. Without scripted managers, the accelerated world would run with
nobody but the built-in AI in it, and the AI only exercises what it was written
to do.

A handful of LLM managers, each with a different personality, play the same
game a human would, through the same API, under the same rules. They reach
the code paths a human would reach: the transfer market, the development
squad, the sponsor choice, the insolvency ladder. They also say so when the
game contradicts itself. The models need not be clever. The subtle problems
are left to the human beta in milestone 3. These testers are there to catch
what is plainly wrong.

## Player experience

There are five testers. Each one manages its own team in the staging world,
next to the eleven teams the AI runs. Each one has a persona that shapes how it
plays: a **youth builder** who opens and upgrades a development squad and lives
off its graduates; an **aggressive trader** who buys and sells at auction every
visit; a **money-focused manager** who chases sponsorship and keeps the wage
bill low; a **racer** who picks a squad for every race's course; and a
**minimal-effort manager** who rarely visits and leaves most things to their
defaults.

A tester visits about every eight real hours, which is about every eight game
days. The minimal-effort tester visits once a real day. Visits are spread out so
the testers do not arrive together. On each visit a tester first reads its own
diary: a short note it wrote at the end of each earlier visit, saying what it
did, what it expected to happen next, and what it was watching. It then looks
at its team the way a player would: the dashboard, the finances, the roster,
the calendar, the market. It acts according to its persona, and checks whether
the game did what its last diary entry expected. A tester does not see the
game's code. It knows the game only from a one-page player's guide, the
staging briefing about the accelerated clock, and the API's own documentation.

The testers know they are beta testers. When something looks wrong, such as
money that doesn't add up, a rider in two places, a rule in the guide that the
game doesn't follow, an error to a valid request, or two screens that disagree,
a tester files a report through the game's own report-a-problem channel (#131),
saying what it expected and what it saw. Before filing, it reads its own earlier
reports and doesn't file the same one twice. It never files more than three on
one visit. The operator reads the reports in Django admin, as for any human
reporter.

The visit ends with a new diary entry. The operator can follow each tester's
diary in the repository, read every visit's full log on GitHub, and pause all
the testers at once with a single switch.

If a tester loses its team, through insolvency or the inactivity release, it
says so in its diary and reports it if it looks wrong. On its next visit it
claims a free team and keeps playing.

## In scope

1. Five testers, each with its own account, team, persona and diary.
2. Visits on a schedule: about every eight real hours for four of the testers
   and once a real day for the minimal-effort one, staggered so no two visit
   at the same time.
3. On each visit, a tester reads its last few diary entries, plays its team
   through the public API only, files at most three reports, and writes one
   new diary entry.
4. The tester's instructions are: its persona, that it is a beta tester whose
   job is finding problems, how to file a good report, the staging briefing
   (`world/STAGING_BRIEFING.md`) as it stands, and a one-page player's guide
   to the rules.
5. A one-page player's guide, written from the player-facing rules only.
6. Reports go only to the in-game report channel. Each says what the tester
   expected and what it saw. A tester checks its own earlier reports before
   filing.
7. Each tester's diary can be read in the repository, on its own branch, and
   every visit's full log can be read on GitHub.
8. A tester that has no team claims a free one on its next visit.
9. A failed visit, whether the server is down, the model provider refuses or
   the free quota is used up, is skipped and logged. It is not retried in a
   loop, and the next visit goes ahead as normal.
10. One switch pauses every tester and turns them back on.
11. A setup step, run once per tester by the operator, creates the tester's
    account, claims a team for it and gives the operator a key to store.
12. The testers run on a free model tier (Gemini Flash-Lite). Changing provider or model
    is a setting, not a rewrite.
13. Everything can be run against a local server before it runs against
    staging.

## Out of scope

- **The real-time cadence** for the human beta (once or twice a real day).
  That is a settings change made with #133, not part of this ticket.
- **Marking accounts as agents.** That is #134.
- **A dashboard for watching the testers.** The diaries and the run logs are
  enough. Later, if they prove not to be.
- **Testers seeing each other's reports.** Two testers may report the same
  bug, and the operator deduplicates during triage.
- **Filing GitHub issues automatically.** The operator triages and files issues
  by hand (#131's triage).
- **Reading the code.** The testers judge the game as a player would, never by
  its source.
- **A clever or expensive model.** No. A free tier is enough for plain bugs,
  and the human beta catches the subtle ones.

## Rules and edge cases

- **Same game, same rules.** A tester uses only what a human player can use,
  and sends the same requests a player's API client would, with its own key.
  It counts as active for the inactivity rule like anyone else.
- **Limits.** A tester stays within the API's 60 requests a minute and the
  report channel's 20 reports per 24 real hours. At three reports a visit and
  at most three visits a real day, it cannot reach the report limit. The model
  provider's free tier allows a limited number of calls a minute and a day,
  shared by all the testers, so they visit one at a time and their cadence
  is set by that allowance.
- **Bounded visits.** A visit has a cap on how many steps it can take, so a
  confused tester cannot loop for an hour or burn the free quota. A visit that
  hits the cap still writes its diary entry and says it was cut short.
- **Speed artefacts.** The staging briefing lists what the accelerated clock
  makes look odd. A tester is told not to report those.
- **No team.** A tester that has lost its team, or never had one, claims a free
  team. If none is free, it writes that in its diary and ends the visit.
- **Server down.** The visit fails early, the run log says why, and the diary
  is not changed.
- **Diary length.** A tester reads only its last few entries, so a long-running
  diary doesn't fill its instructions.
- **Paused.** While paused, no visits happen at all. Four paused real days is
  longer than the inactivity release, so a long pause means the testers lose
  their teams. That is expected, and pausing is meant for short fixes. For a
  long pause, freeze the staging clock as well (#129).

## Decisions taken

- **Runner:** a scheduled GitHub Actions workflow running a small script in the
  repo, so every visit has a log and the harness can be run against a local
  server.
- **Model provider:** Gemini Flash-Lite's free tier, about 500 calls a day and
  no card. Mistral was chosen first, but its Free plan only activates API keys
  after you buy $10 of credits, and Mario would rather not pay. OpenCode's free
  models answer only its own client. Groq's free tier is too small (200K tokens
  a day), and Cerebras has dropped its free tier. Claude Haiku 5.5, at about $5
  per staging season, remains the paid fallback. Prompts on a free tier may be
  used for training, which is acceptable because the game data is made up.
- **Smart models aren't needed.** The human beta catches subtle issues (Mario).
- **Five testers**, with the personas above, leaving eleven teams to the AI.
- **Cadence:** every eight real hours, staggered (four hours was agreed first
  and halved to fit the free tier's daily calls), and once a real day for the
  minimal-effort tester.
- **Diary:** on a dedicated `beta-diaries` branch, one file per tester.
- **Knowledge:** a one-page player's guide written for this ticket, plus the
  staging briefing and the API docs. Never the code.
- **Tester instructions** say plainly that they are beta testers whose job is
  finding problems, and how to report one (Mario).
- **Reports:** at most three per visit, checked against the tester's own
  earlier reports. In-game channel only.
- **Losing a team** is not the end. The tester claims another.

## Open questions

None.

## Deferred

- **Real-time cadence** with #133/#134, since staging comes first.
- **A tester activity dashboard,** if the diaries and logs turn out not to be
  enough to follow along.
