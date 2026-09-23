# Strip the mock UI and require login

**Status:** implemented
**Domain(s):** `frontend/`, `api/`
**One-liner:** The game shows only what it actually has, and you have to log in to see any of it.

## Why this exists

The app currently claims to be a much bigger game than it is. The sidebar
advertises sixteen destinations and six of them work; the other ten open a
screen that prints its own path. The Dashboard is worse — it is almost entirely
invented, and it is invented convincingly: a budget in euros, a divisional rank,
a league table of teams that do not exist, riders who do not exist finishing
races that never happened, and an inbox describing three features the game has
never had. None of it is labelled as fake.

This is about to be played by a person for the first time — register, claim a
team, pick a squad, watch a race, check the table. That pass is worthless while
the screen is half fiction, because a tester cannot tell a feature that is
missing from one that is broken. The second half of the ticket is the same
problem from the other end: an anonymous visitor who has never logged in is
handed the full game chrome and whatever each screen renders when its data
request is refused, which is a convincing impression of a broken game rather
than a closed door.

## Player experience

A visitor arrives at the game and sees a login screen. There is nothing else to
look at — no sidebar, no dashboard, no calendar, no table. If they follow a link
a friend sent them to a specific screen, they still get the login screen first,
and once they have logged in they land on the screen they were trying to reach
rather than being dumped at the front door. If they have no account yet they can
register from here, and a newly registered manager who has not yet claimed a
team can reach exactly one screen: the one that gives them a team.

A manager who logs in sees a sidebar with six things on it, and all six work.
There is nothing to click that explains it is not built yet, and no little
number badges promising unread messages. The rest of the game is not hinted at;
when transfers exist, transfers will appear.

The home screen is small and every word on it is true. It greets them by the
name they registered under, not an invented one, and names their actual team.
It tells them where they are in the season — which week of which season — and
where their team sits in the standings, which early in a season means level with
everyone on nothing. It shows the next race that has not yet been run, and
whether they have chosen a squad for it or whether the game will choose one for
them. That last line is the only thing on the screen that asks them to act, and
it is the reason the screen exists at all.

While any of this is still loading, they see nothing in its place rather than a
plausible-looking number that later changes. A manager refreshing the page mid-
session is not thrown back to the login screen while the game works out who they
are. And if they type or bookmark a URL that no longer exists — `/transfers`,
say, from before this change — they land on the home screen rather than on an
error.

## In scope

1. Every sidebar destination opens a screen that is built: Dashboard, Roster,
   Staff, Calendar, Results, League table. There are six, and no others.
2. The sidebar keeps its section grouping, minus any section left with no items.
3. No sidebar item carries a count badge, and no badge can be added to one — the
   notion of a badge is gone, not merely unused.
4. The screen that announced an unbuilt feature no longer exists. Any path the
   game does not recognise takes a logged-in manager to the home screen.
5. The home screen shows, and shows only: the logged-in manager's own name, their
   real team's name, the current season and week, their team's own position and
   points in the standings, and the next race that has not been run — with its
   name, its date, and whether this team has chosen a squad for it.
6. No element of the home screen displays a value the game cannot supply. Where
   a mockup element has no real source, it is removed rather than approximated.
7. The team name and manager name shown anywhere in the app chrome are the real
   ones for the logged-in manager.
8. While a piece of the home screen is still loading, that piece renders nothing
   rather than a placeholder that resembles data.
9. A visitor with no session can reach the login and registration screens and
   nothing else. Any other address sends them to the login screen.
10. After logging in, the manager lands on the screen they originally asked for;
    if they asked for nothing in particular, the home screen.
11. A logged-in manager without a team can reach only the claim screen and the
    auth screens, as today.
12. A logged-in manager who already has a team cannot reach the claim screen; it
    sends them to the home screen.
13. Logging out lands on the login screen.
14. A manager who reloads the page, or opens a deep link in a new tab, is never
    shown the login screen while the game is still establishing who they are.
15. The game exposes no information at all to a visitor who is not logged in.
    The three requests that previously answered anyone — the clock, the season
    position, and the race calendar — now require a session like everything else.

## Out of scope

- **Redesigning or restyling anything.** This removes; the mockups in `design/`
  remain the reference for every screen, including ones not yet built.
- **Building any of the removed screens.** Training, Tactics, Race day,
  Transfers, Scouting, Contracts, Rankings, Finances, Sponsors, Facilities and
  Inbox each have their own ticket. Removing the link is not a decision about
  the feature.
- **The race detail screen**, reached by clicking a race on the calendar. It is
  real and untouched.
- **A dedicated "page not found" screen.** *Later* — worth building when there
  are enough screens to get meaningfully lost among.
- **A public landing page or anything else a logged-out visitor can look at.**
  *Later*, and it needs a reason to exist beyond the login screen looking bare.
- **Restoring the form watch, the deadline countdown, the course profile, or the
  inbox in any form.** *No.* Each belongs to a feature that does not exist —
  rider freshness, a real entry deadline, course markers, and messaging
  respectively — and each will be designed by that feature rather than recovered
  from the mockup.
- **Password reset and the rest of account self-service.** Belongs to its own
  ticket; this one only decides who may see the game, not how they recover
  access to it.

## Rules and edge cases

**The next race** is the next race on the calendar that has not finished,
regardless of which team is looking — every team is entered in every race, so
there is no such thing as a race a manager is not in. When no unfinished race
remains, the home screen says the season has no races left rather than showing
an empty card.

**"Squad not set" does not mean "not racing."** A team that never opens the
squad screen still starts, with a squad the game picks. The home screen must say
which of the two it is, because the whole value of the line is the nudge to
choose deliberately instead of accepting the automatic pick.

**A brand-new team is not an error state.** A manager who has just claimed a
team has riders but no results, and sits in the standings on zero points level
with everyone else. The home screen reads as a season that has not started, not
as something that failed to load.

**Loading is not a state worth illustrating.** Any part of the home screen whose
data has not arrived shows nothing at all. A skeleton that resembles the real
thing reintroduces exactly the confusion this feature removes.

**Establishing identity is not the same as having no session.** The game asks
who is logged in once, when it starts; until that answer arrives nobody is
redirected anywhere. Bouncing a logged-in manager to the login screen because
the answer had not come back yet is the one failure this feature must not have.

**The two access rules compose in order.** No session sends you to the login
screen; a session without a team sends you to the claim screen. A visitor with
no session never sees the claim screen, and a manager with a team never sees it
either.

**Closing the public endpoints is a deliberate reversal.** The clock, season
position and calendar were previously readable by anyone, on the argument that
world data is a shop window for a visitor deciding whether to sign up. That
argument is rejected: the game shows nothing until you are in. This must be
recorded as the current decision rather than left looking like an oversight, so
that a future landing page reopens it knowingly.

## Decisions taken

- **Does the Dashboard survive?** Yes, as a small real home screen — manager,
  team, season position, standings row, next race and its squad status. It is
  the only screen that answers "what should I do now", which is worth keeping
  even when thin.
- **What happens on an unrecognised path?** Redirect to the home screen. The
  earlier argument for a visible placeholder was about a scaffold with ten fake
  routes; with every route real, there is nothing left to diagnose.
- **Sidebar structure?** Keep the section grouping and drop sections left empty,
  so re-adding a screen later is a single change rather than a restructure.
- **Should the backend require login too?** Yes — everything, including the
  clock, season position and calendar. No shop window. `api/README.md` is
  updated as part of this work, since it currently argues the opposite.
- **Where does a manager land after logging in?** On the page they originally
  asked for, so that deep links and shared links survive the guard.
- **Can a manager with a team reach the claim screen?** No; they are sent to the
  home screen. The backend already refuses a second claim, and the interface
  should not offer an action that cannot succeed.
- **Do the count badges go?** Yes, along with the ability to have one at all —
  every badge belonged to a removed screen, and a facility nothing uses is the
  same scaffolding this ticket exists to clear.
- **Does the course profile survive with real data?** No. The game has no
  per-race course shape to draw, so the element goes entirely rather than
  becoming an empty frame.

## Open questions

None.

## Deferred

- **A "page not found" screen.** Waiting until there are enough screens for a
  wrong address to be a plausible mistake rather than a typo.
- **A public landing page, or any view of the game for logged-out visitors.**
  Waiting for a reason beyond aesthetics; reopening it means revisiting the
  decision to close the three public endpoints.
- **Rider form on the home screen.** Waiting on rider freshness (#59), which
  will decide what form even is.
- **A real entry deadline and its countdown.** Waiting on a deadline concept;
  the game's clock currently moves a week at a time, and the mockup's countdown
  implies something finer.
