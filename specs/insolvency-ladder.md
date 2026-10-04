# Insolvency: act or lose the team

**Status:** proposed
**Domain(s):** `economy/`, `teams/`, `transfers/`, `staff/`, `riders/`, `world/`, `api/`, `frontend/`
**One-liner:** A managed team whose balance is negative after payday is told exactly how much weekly spending to cut and by when; a manager who cuts it keeps the team, one who doesn't loses it.

## Why this exists

Every money system in the game assumes money can run out, and nothing says what
happens then. A negative balance is flagged and otherwise ignored, so
overspending has no consequence beyond a red number. That makes the spending
decisions — signing riders, hiring staff, bidding, funding a development squad —
cheaper than they should feel.

This gives a negative balance consequences, while keeping them fair. A team
that falls behind is warned, locked out of adding cost, and given a concrete,
achievable target. A manager who reads it and acts keeps their team. The loss of
the team is the price of not acting, not an unavoidable fate.

## Player experience

Payday runs and a manager's balance is below zero. A banner appears on the
dashboard and the finances screen: *Your team is insolvent. Cut $X of weekly
spending by <date> or you will lose the team.* It shows how much has been cut so
far, what is left, and the deadline. Nothing has been taken from them. From this
moment the team cannot add cost: no signing free agents, no bidding, no hiring
staff, no opening or upgrading a development squad. Any bid they already had
standing is withdrawn.

The target is the gap between the team's regular weekly outgoings (rider wages,
trainer salary, development squad cost) and its regular weekly income (merchandise
and sponsorship at its promised base). Every lever counts toward closing it.
They can list a rider for a forced sale: the rider leaves the team immediately,
the wage stops at once, and if a buyer wins the auction the team receives the
money. If nobody bids, the rider becomes a free agent and the team gets nothing.
They can also fire the trainer, close the development squad, or sign a sponsor,
which adds income. Forced listings cost no severance, but they cannot be taken
back.

When the weekly gap closes, the escalation stops: the banner changes to a
"recovering" notice and the deadline disappears. The embargo stays until a payday
ends with a balance of zero or more, at which point it lifts and the team is
solvent again. If the gap is still open when the fourth consecutive insolvent
payday arrives, the team is released to the unmanaged pool. The manager sees the
same "you lost this team" message as any other loss, with insolvency as the
reason.

## In scope

1. A managed team is insolvent when its balance is negative after the weekly
   payday settlement.
2. On becoming insolvent: the team is embargoed, a warning appears on the
   dashboard and finances screen, and live auction bids by the team are withdrawn.
3. While embargoed, the team cannot sign free agents, bid on auctions, hire
   staff, or open or upgrade a development squad. Each refused action says why.
4. The warning shows the weekly shortfall to close, the amount closed so far and
   the deadline.
5. The shortfall is the team's regular weekly outgoings minus its regular weekly
   income; firing a trainer, closing the squad, signing a sponsor and shedding
   riders all count toward it.
6. A forced sale is available from the first insolvent payday. Listing a rider
   removes them from the roster at once and stops their wage.
7. A forced-sale rider is auctioned; a sale pays the team, no sale makes the rider
   a free agent, and in both cases no severance is charged.
8. Forced listings are labelled as forced in the market, and cannot be withdrawn.
9. A forced sale cannot take the roster below the number of riders needed to race.
10. The target is re-checked every payday. Meeting it stops escalation; a new
    breach (a salary review raising wages, say) starts a fresh deadline.
11. The embargo lifts only when a payday ends with a balance of zero or more.
12. A team still short of its target at its fourth consecutive insolvent payday is
    released to the unmanaged pool, and its manager sees why.
13. Insolvency carries across a season boundary unchanged.

## Out of scope

- **The game listing riders for an inactive manager.** Cut: decided "act or lose".
  An absent manager simply reaches the loss rung.
- **A separate forced-sales rung.** Cut: the lever is open from the first
  insolvent payday, so weeks 2–3 of the brief's ladder have nothing of their own.
- **Breaking staff contracts.** Cut: firing and closing are already the manager's
  to do, and now count toward the target.
- **A debt floor.** Cut: balances stay unbounded below, as decided for the ledger.
- **Points deductions and AI half-takeover.** No: rejected in the brief.
- **Insolvency for unmanaged teams.** Later, once unmanaged teams earn income.

## Rules and edge cases

- Only managed teams can become insolvent. A claim clears any insolvency on the
  team, since the claim resets its balance.
- An absent manager loses the team in roughly three weeks, sooner than the ten
  in-season weeks the inactivity rule allows. Money runs on its own clock.
- A manager who cannot meet the target even by listing every rider above the
  roster minimum and using every other lever loses the team. That is accepted.
- A rider with a live auction already running can be forced-listed: the existing
  listing becomes the forced one.
- Going insolvent on purpose to dump riders without severance is possible. The
  embargo and the deadline are the price, and are considered enough.
- A forced sale that fails to sell still counts as shed the moment the rider is
  listed, so the manager is never waiting on a buyer to learn whether they are safe.
- The weekly payday settlement still runs normally while insolvent; wages are
  charged and the balance can go further negative.

## Decisions taken

- Trigger: negative balance after the weekly payday settlement, not "can't cover
  next week" and not several negative weeks running.
- Survival: act or lose. No auto-listing by the game, no balance-only recovery.
- Target: close the weekly gap between regular outgoings and regular income,
  counting trainer salary and squad cost as levers, not wages alone.
- Unmanaged teams are excluded from the ladder.
- Forced listings are free of severance, irreversible, and labelled as forced.
- Insolvency carries across season boundaries.
- Loss comes at the fourth consecutive insolvent payday with the target unmet.
- The embargo outlasts the escalation: it lifts only at a non-negative balance.

## Open questions

None.

## Deferred

- **Runway projection ("N weeks of money left")** — the target and deadline already
  cover the urgent case.
- **Out-of-game notification** — needs email delivery, which is #51.
- **Insolvency for unmanaged teams** — revisit once #45 gives them income.
