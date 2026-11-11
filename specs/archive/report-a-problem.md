# Report a problem

**Status:** implemented
**Domain(s):** a new `feedback/` domain, `api/`, `frontend/`
**Issue:** #131
**One-liner:** Anyone playing the beta, human or LLM, can report a problem from wherever they are in the game, and every report lands in one triage list with the context needed to act on it.

## Why this exists

The staging beta (milestone 1) is played by LLM managers on an accelerated
clock, and later by a handful of human testers. Their main job is finding what
is broken, wrong-looking or unbalanced. Today there is nowhere in the game to
say so. Reports would arrive scattered across chat logs and agent transcripts,
each in a different shape and most missing the one fact that makes them
actionable: which team, which week, which screen, and when.

This feature gives both kinds of tester the same single channel. The game
attaches the context itself, so a report says *what* the tester noticed and the
game says *where and when*. Someone triaging can then work through one list,
merge the six reports of the same deficit into one GitHub issue, and let each
reporter see that their report was dealt with.

## Player experience

A tester is on the Finances screen and the wage bill looks wrong. In the frame
around every screen there is a **Report a problem** button. They press it and a
small form opens over the screen they were on, so they don't lose their place.
They pick what kind of report it is (a bug, something that looks wrong, a
balance concern, or a suggestion), write what they saw in their own words, and
send it. The form closes and they are told the report was received.

If sending fails, because the connection dropped or the server refused it, the
form stays open with their text still in it and tells them why, so they can try
again without retyping.

An LLM manager does the same thing through the API: it sends a category and its
text, and gets the report back with the context the game attached. Before it
reports something it can list its own earlier reports and see which ones are
still waiting, which were turned into a GitHub issue (with the link), and which
were dismissed. That stops it filing the same thing every game week.

Behind the scenes a staff member opens the triage list, sees new reports
first, filters by category, outcome, team or reporter, and reads each with its
attached context. For each one they either file or find a GitHub issue and mark
the report triaged with that link, mark it triaged with no issue, or dismiss it,
and they can leave themselves a private note. The reporter sees the outcome,
never the note.

## In scope

1. A **Report a problem** button is visible on every screen a logged-in user
   can reach, including the claim-a-team screen for a user with no team.
2. Pressing it opens a form over the current screen; closing the form returns
   the user to exactly where they were.
3. The form asks for a category (bug, looks wrong, balance, suggestion) and
   free text. Both are required; a report with empty text cannot be sent.
4. On success the form closes and the user is told the report was received.
5. On failure the form stays open with the user's text intact and says what
   went wrong.
6. Every report automatically records: who sent it; the team they managed at
   the time, if any; the season and week, and the in-game date and time, if a
   season is running; the real date and time it was sent; and the screen (for
   the SPA) or the address they were on.
7. The team recorded on a report stays the team it was filed against, even if
   that team is later released or claimed by someone else.
8. The same reporting is available through the API to any logged-in caller,
   with no difference in rules between the SPA and an agent.
9. A reporter can list their own reports, newest first, each showing its
   category, text, when it was sent, its outcome, and the GitHub issue link if
   one was attached.
10. A reporter cannot see anyone else's reports.
11. Each account can send a limited number of reports per day. Past the limit
    the report is refused with a plain message saying so and when it can try
    again. The limit is generous enough that no honest tester meets it.
12. Staff can list all reports, newest first, filter them by category,
    outcome, team and reporter, and read each one with its context.
13. Staff can set a report's outcome to **new**, **triaged** or
    **dismissed**, attach a GitHub issue link, and write a private note.
    The reporter sees the outcome and the link but not the note.

## Out of scope

- **Automatic GitHub issues.** No: a person curates first, so the same problem
  seen by six agents becomes one issue, not six.
- **Screenshots and attachments.** Cut: text plus the captured screen is
  enough for the beta, and uploads bring storage and moderation with them.
- **A picker for which rider, race or team the report is about.** Cut: the
  reporter names it in the text.
- **Seeing other people's reports.** No: independent reports of the same bug
  are a signal; de-duplication is triage's job.
- **An in-app "my reports" screen.** Later; the list exists in the API.
- **A triage agent that groups duplicates.** Later.
- **A Spanish label for the button and form.** Later; comes with #137.
- **API tokens.** Belongs to #130. Until then agents report through a session
  login, exactly like the SPA, and nothing here changes when tokens arrive.

## Rules and edge cases

- Logged-out visitors cannot report, so the login and register pages have no
  button.
- A user with no team can report; the team is simply left empty.
- Between seasons, or before the first season is declared, the in-game
  context is left empty rather than guessed. The real time is always recorded.
- The context is captured at the moment of sending. Nothing about it is
  recalculated later.
- The screen recorded is the one the reporter was on when they pressed the
  button, not the form itself.
- A report cannot be edited or withdrawn by its reporter once sent.
- Reports are never deleted by the game. A user who is removed takes their
  reports with them only if staff delete the account.
- Very long text is refused with a message, rather than silently cut.
- Only the outcome, the link and the private note change after sending; what
  the reporter wrote and the captured context never do.

## Decisions taken

- Automatic GitHub issues or curated first? **Curated.** A person or later a
  triage agent files the issue and links it back.
- Who can report? **Any logged-in account, team or not.**
- What does the reporter see afterwards? **A confirmation, and through the API
  a list of their own reports with outcomes.** No screen yet.
- Can reporters see others' reports? **No.**
- What goes into a report? **The four categories, required free text and the
  automatic context.** No attachments, no subject picker.
- A cap on volume? **Yes, a generous daily limit per account, refused with a
  plain message.**
- Triage outcomes? **New, triaged (optional GitHub link), dismissed, plus a
  private note.** The reporter sees outcome and link, not the note.
- Game time and real time are both recorded, because on staging's accelerated
  clock they drift apart quickly.
- Triage happens in Django admin, by staff.

## Open questions

None.

## Deferred

- An in-app "my reports" screen: wait for the human testers in milestone 3.
- A triage agent that groups duplicate reports: wait until there is a volume
  of reports worth grouping.
- Spanish copy for the button and form: ships with #137.
