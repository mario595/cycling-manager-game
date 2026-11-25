# Rider departures, and the graduate's deadline

**Status:** approved
**Domain(s):** riders, transfers, world, api, frontend
**One-liner:** When a rider leaves your team or development squad while you are away, the game tells you who went, when and why; and a graduate shows the exact week they will be released if you do nothing.

Issues: #158, #162.

## Why this exists

The LLM beta testers came back to a new season with rosters two riders shorter and could not say why (#158). The cause was age retirement at the season close, which is warned about for a whole season with a "final season" tag, but once it happened there was no trace of it: the riders were simply gone, and the only sign was a smaller wage bill. In the same review, two testers let every development squad graduate be released to the free agents without noticing (#162). The squad screen did count down "Decide within N weeks", but it never said what happens at zero, never named the week, and after the release the riders just vanished from the squad.

Both are the same gap: things happen to a manager's riders between visits, and the game keeps no record a manager can read. This adds one: a team's departures, each with the rider, the week and the reason. It also makes the graduate's deadline a date with a stated consequence, and puts both on the dashboard, where a returning manager looks first.

## Player experience

A manager comes back after the season close. The dashboard has a "Riders who left" card: *Carlos Ruiz (CLB, 36) retired at the end of Season 3*, *Diego Mora (SPR, 34) retired at the end of Season 3*. Each name links to the rider's profile. The roster screen has the same list for the season so far, with last season's retirements included, so the shrunken roster has its explanation next to it. The last two weeks of the previous season had already shown a line on the dashboard: *2 riders retire at the end of this season*, linking to the roster, where the "final season" tags mark which riders.

On the development squad screen, each graduate now reads *Decide before Season 4, Week 6 (2 weeks left). If you do nothing, they're released to the free agents.* While any graduate is undecided, the dashboard shows *2 graduates are waiting for your decision*, linking to the squad. In a graduate's last week it turns urgent: *released at the start of next week*. If the manager still does nothing, the graduates leave at the next week boundary. The squad screen and the dashboard then say *Luis Garcia (SPR, 19) was released to the free agents in Season 4, Week 6*, and the profile link shows where he is now, still signable in the free-agent pool if nobody has taken him.

A rider sold at auction while the manager was away also appears: *Pablo Fernandez (ROU, 24) was sold to Baleares Ciclismo for $412,000 in Season 4, Week 3.*

Everything shown on the screens is also in the API: each departure, and each graduate's deadline week.

## In scope

1. A departure is recorded when a team's rider retires by age at the season close, when a graduate is released to the free agents (their window closed, or their auction ended unsold), and when a rider the team listed is sold at auction, including a forced sale.
2. Each departure says who the rider is (name, speciality and age at the time, plus a link to their profile), when it happened as a season and week, and why. A sale also names the buyer and the fee.
3. Departures the manager causes directly in that moment are not recorded: releasing a rider, discarding or promoting a squad rider, and closing the squad.
4. The dashboard shows departures from the last two game weeks. It shows nothing when there are none.
5. The roster screen lists this season's departures, plus the retirements at the last season close.
6. The development squad screen lists this season's graduate releases.
7. The API returns the team's full departure history, newest first.
8. Each graduate shows the week they will be released in, both as a season and week and as weeks left, with the sentence saying what happens if nothing is done. If that week is not in the calendar yet, only the count is shown.
9. The dashboard shows a cue whenever the team has undecided graduates. It turns urgent in a graduate's last week.
10. In the last two weeks of a season, the dashboard says how many of the team's riders retire at the end of it, and links to the roster.

## Out of scope

- **Departures the manager caused with a click** (release, discard, promote, squad close): No. The manager was there when it happened.
- **A general inbox or news feed** for every event in the game (race results, sponsor changes, bids): Later. This is one specific feed. If the game grows a general inbox, departures should move into it.
- **Notifications outside the game** (email, push): Later. They belong with the real-time beta.
- **Records for teams nobody manages**: these teams get records too, because that is simpler and harmless. Nothing shows them, and a manager who claims one of these teams later sees its history.
- **Making rider names unique** (#162's side note): No. Speciality and age next to the name, plus the profile link, are enough to tell riders apart.
- **Backfilling departures that happened before this ships**: No. Staging is being reset anyway.

## Rules and edge cases

- A retirement is dated to the closing season's final week. That matches the rider profile's "Retired · Season N, Week W" label and reads as "at the end of Season N".
- A graduate whose auction is still open when their window closes is not released, and the auction decides what happens (existing rule). Sold, they appear as a sale. Unsold, they appear as a release in the week the auction ended.
- The deadline week is the week at whose start the graduate is released, so "Decide before Season 4, Week 6" means it is still the manager's decision throughout Week 5. The window can cross a season boundary, so the deadline can name the next season.
- A team's departures stay with the team. If the team changes manager, the new manager sees the old departures in the API history. The screens only show recent ones, so these quickly drop out of view.
- A rider who leaves the game still appears in the record by name, with the speciality and age they had at the time.
- The retirement line counts only riders still on the roster. A tagged rider who has since been sold does not count.

## Decisions taken

- One record for both tickets, rather than two mechanisms: yes (Mario, 2026-11-25).
- Which departures are recorded: those that happen while the manager is away (retirement, graduate release, sale at auction). Manager-initiated ones are not.
- How long departures show: the last 2 game weeks on the dashboard, this season plus the last close on the roster, and the full history in the API.
- Deadline wording: "Decide before S W (N weeks left). If you do nothing, they're released to the free agents." The count alone is shown when the week isn't declared yet.
- Graduate cue: shown whenever there are undecided graduates, and urgent in the last week. The ticket's "due this week or next" would always be true with a 2-week window.
- Retirement warning: a dashboard line in the last 2 weeks of the season only.

## Open questions

None.

## Deferred

- A general in-game inbox, which this feed would fold into. Wait until a second kind of event needs it.
- Email or push notifications. Wait for the real-time beta.
