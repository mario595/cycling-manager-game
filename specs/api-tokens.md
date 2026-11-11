# API tokens and API docs

**Status:** approved
**Domain(s):** `accounts/`, `api/`, `world/` (inactivity), `config/`
**Issue:** [#130](https://github.com/mario595/cycling-manager/issues/130)
**One-liner:** A manager can play the game through its API with a personal
token instead of a browser login, and can read a documentation page that
explains every action in game terms.

## Why this exists

The staging beta (milestone 1) is played by LLM managers, not people
([#132](https://github.com/mario595/cycling-manager/issues/132)). Today the
only way into the game is a browser session: log in through the SPA, carry a
cookie, send a CSRF token with every write. An agent can fake that, but it
would be playing through a side door, and the point of the beta is that agents
play **the same game, through the same endpoints, under the same rules** as a
human. If they don't, the bugs they find aren't the bugs humans will hit.

Agents also need to discover what they can do. A human learns the game from
the screens; an agent learns it from a description of the endpoints. That
description has to say what each action means in the game — "list a rider for
auction at half their value" — not just which fields a request takes, because
an agent will read every word and act on it.

## Player experience

Mario sets up a beta manager. The account already exists, made the ordinary
way through registration. He runs one command naming the account, and it
prints a long token, once. He hands it to the agent's harness. If he loses
it, there is no way to read it again: he runs the command again, which issues
a new token and stops the old one working.

The agent sends that token with every request. From the game's point of view
it is now that manager: it sees the manager's team and nobody else's, picks a
squad, sets training, bids in auctions, signs a sponsor — anything the SPA
can do, and nothing it can't. Every rule the game enforces on a human it
enforces on the agent, with the same refusals and the same messages.

Before it plays, the agent opens the API documentation, a page listing every
endpoint with a plain-language account of what each action does in the game,
what it costs, and when it is refused. The page is behind login like
everything else, and the token is enough to read it.

A badly written agent that loops gets slowed down: past a per-account limit
it is told to wait, and for how long, rather than being able to hammer the
server. A well-behaved agent making one visit's worth of calls never notices
the limit. Human players in the browser are not limited at all.

An agent that keeps playing counts as an active manager. One that stops —
the harness is switched off, or the "rarely logs in" persona overdoes it —
loses its team after ten in-season weeks, exactly like a human who walks away.

When the beta ends, or a token leaks, Mario revokes it with a command, and
the next request using it is refused straight away.

## In scope

1. Each account can hold at most one API token. A command issues one for a
   named account and prints it once. Issuing again replaces the old token,
   which stops working immediately.
2. A command revokes an account's token. The next request using it is
   refused.
3. Once issued, a token cannot be displayed or recovered again, by Mario or
   by anyone reading the database.
4. A request carrying a valid token is treated as coming from that account,
   on every endpoint the SPA uses, with the same permissions and the same
   game rules. There are no token-only endpoints and no token-only
   shortcuts.
5. A request with a missing, malformed, unknown or revoked token is refused
   with a plain "not authenticated" answer. It never gets a redirect or an
   HTML login page.
6. Writes made with a token work without any browser-only step, such as
   fetching a CSRF cookie first.
7. Any request made with a token counts as the manager being seen, for the
   purposes of the inactivity rule that releases a team after ten in-season
   weeks without the manager showing up.
8. Token requests are rate limited per account. A burst of a few dozen calls
   (one visit) is fine; sustained hammering, around sixty a minute or more,
   is refused with a "too many requests, retry in N seconds" answer. Browser
   sessions are not limited.
9. A machine-readable description of the whole API, and a human-readable
   documentation page built from it, both available to any logged-in user
   (by session or by token) and to nobody else.
10. Every endpoint in that documentation says what the action does in game
    terms: what it changes, what it costs, when it is refused, and which
    numbers are shown on which scale (for example the 0–10 attribute scale,
    or whole-unit money).
11. Every endpoint has been checked for anything that assumes a browser. Each
    one is either fixed so a token client can use it, or recorded as
    browser-only with the reason.

## Out of scope

- **A token screen in the SPA's account settings.** *Later*: no human needs
  a token during the staging beta. Comes with account self-service
  ([#51](https://github.com/mario595/cycling-manager/issues/51)) if ever.
- **Several tokens per account** (one per device or tool). *Later*: no use
  for it yet.
- **Token expiry.** *Later*, if at all: a staging season lasts about 3.5 real
  days, and an expiring token would break an agent partway through one.
- **Agent-only endpoints, bulk actions, or anything that lets an agent do
  what a human can't.** *No*: the ticket rules this out, and it would make
  the beta test a different game.
- **JWT or refresh tokens.** *No*: the extra machinery solves a cross-domain
  problem this game doesn't have.
- **Creating agent accounts.** Belongs to #132. The existing registration
  already does it.
- **Marking an account as an agent, invite-only registration.** Belongs to
  [#134](https://github.com/mario595/cycling-manager/issues/134).
- **Writing the game rules out for agents.** Belongs to #132's prompting. The
  docs describe the actions, not the strategy.

## Rules and edge cases

- An account with no team can still hold a token. It sees what any teamless
  logged-in user sees, and can claim a team through the API like a human
  through the SPA.
- Token users and browser users are indistinguishable to the game itself:
  the same account can use both at once, and nothing in play depends on
  which one was used.
- Logging out in the browser does not revoke the token, and revoking the
  token does not log anyone out of the browser. They are separate.
- An account that has never logged in, but uses a token, is now seen. So the
  inactivity rule, which used to skip never-seen accounts, now applies to it
  from its first token request.
- The rate limit counts per account, not per token or per address, so
  reissuing a token does not reset it.
- The documentation is generated from the API itself, so an endpoint added
  later appears in it automatically. Its game-terms description still has to
  be written by whoever adds it.
- Endpoints that return a file rather than data (a race replay log) are
  documented as such.

## Decisions taken

- **Who gets a token:** any account, issued by an operator command. No
  self-service screen. (Mario: defaults.)
- **How many and how long:** one per account, no expiry, reissue replaces,
  revoke is immediate. (Mario: defaults.)
- **Recoverable?** No. The token is shown once and stored so it cannot be read
  back. (Mario: defaults.)
- **Throttling:** per account, token requests only, roomy for one visit and
  around sixty a minute sustained, with a retry-after answer. (Mario: defaults.)
- **Docs visibility:** logged-in users only, by session or token, matching
  "the game shows nothing to visitors". (Mario: defaults.)
- **Token use counts as being seen:** yes, so inactivity release applies to
  agents. (Mario: defaults.)
- **Scope split** (MVP / Later / No as above): agreed by Mario, 2026-11-11.

## Open questions

None.

## Deferred

- A token screen for players: when humans need tokens.
- Multiple tokens per account: when a use appears.
- Token expiry: if a long-running real-time beta makes it worthwhile.
