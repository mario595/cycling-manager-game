# Youth triage: promote, develop or discard

**Status:** proposed
**Domain(s):** `riders`, `teams`, `transfers`
**One-liner:** Young riders in a development squad develop for a fixed spell, then graduate — and the manager decides, rider by rider, whether to promote them to the senior team, sell them, or let them go.

## Why this exists

The development squad (#32) and youth intake (#33) deliver two young riders every four weeks, and today nothing can be done with them: they sit in the squad until it is closed, and closing sends them to the free-agent pool. The squad is a dead end. This ticket turns it into a pipeline — riders arrive, develop, and leave by a decision the manager makes.

The decision is interesting only because potential is hidden. A manager cannot read a youngster's ceiling; they can only watch how fast the ratings move and bet. A rider who shoots up in the first weeks is probably a find; one who barely moves probably is not. That is the judgement the hidden-attribute design was built for, and it is what a future scout (#40) will sell information into. Squad places are limited, so every place given to a slow developer is a place not given to the next arrival.

## Player experience

A manager opens the squad screen and sees their prospects. Each shows the usual name, age, speciality and five ratings, plus two new things: how many weeks the rider has left in the squad, and how much each rating has moved since they arrived. The riders are developing on their own — there is no training to set and the senior trainer has nothing to do with them — but not at the same pace. Some jump in their first few weeks, some crawl. Nobody is told which is which; the movement is the only evidence, and it is evidence of a hidden ceiling, not a statement of it.

The squad has a limited number of places, larger at higher levels. The panel shows how many are full. When an intake week comes and there is no room, the arrivals that do not fit are simply lost, and the panel warns beforehand that a batch is about to be turned away. The manager can discard a rider they have given up on, at any time, to make room. The rider vanishes.

After a fixed spell in the squad, a rider graduates. They leave the squad — freeing the place — but are not yet on the senior roster. For a short window they sit as a graduate: no wage, no racing, no training. The manager promotes them to the senior roster, where they draw a salary like anyone else and are trained, raced and valued like anyone else; or lists them on the transfer market without ever taking a roster place; or discards them. If the manager does nothing, the window closes and the rider is released to the free-agent pool, where anyone can sign them. A listed graduate who finds no buyer goes to the same pool.

A manager who closes the squad, or a team that is claimed by a new manager, loses every rider still in the squad outright; riders already graduated are released to the free-agent pool.

## In scope

1. A rider in the squad develops faster than the ordinary age curve alone would take them, at a pace that differs from rider to rider.
2. Every rider ends their squad spell better than they arrived; none exceed their hidden ceiling, and some will end far below competitive level.
3. A fixed number of weeks after arrival, a rider graduates and leaves the squad.
4. The squad has a limited number of places, rising with the squad's level.
5. An intake that does not fit in the free places loses the arrivals that do not fit. The squad panel warns ahead of an intake week that arrivals will be turned away.
6. The manager can discard any rider in the squad or any graduate; the rider is removed from the game.
7. The manager can promote a squad rider or a graduate to the senior roster at any time, unless the roster is full. From then on they draw a salary and are an ordinary roster rider.
8. A graduate takes no roster place, draws no wage, cannot race and is not trained, for a fixed window.
9. A graduate can be listed on the transfer market during the window, under the market's normal listing rules, without being on the roster.
10. A graduate not promoted, listed or discarded by the end of the window is released to the free-agent pool. A listed graduate who goes unsold is released to the pool.
11. The squad screen shows each rider's remaining weeks in the squad and how each rating has changed since arrival. It never shows hidden potential.
12. Closing the squad, or a claim by a new manager, discards every rider still in the squad and releases every graduate to the free-agent pool.

## Out of scope

- **"Retain" as an action.** Keeping a rider is doing nothing; there is no button for it.
- **Demoting a senior rider to the squad.** Would turn the squad into a wage-free parking space. No.
- **A promotion fee.** The squad's own costs already paid for the rider; the price of promotion is the salary that starts.
- **Any way to choose what a squad rider trains.** Development is automatic. Later, if wanted.
- **A faster development rate at higher squad levels.** The level buys better odds of a good arrival and more places, as set in #33; not speed.
- **Revealing a rider's potential.** The scout (#40) is the thing that sells that.
- **Notifications** that a rider is about to graduate or a window is about to close. There is no inbox system yet; the weeks remaining are on the screen.

## Rules and edge cases

- **Spell: 14 weeks.** Counted in in-season weeks from arrival. Chosen so the cap actually binds: arrivals come every four weeks, so a squad at steady state holds about eight riders right after an intake. A Regional squad (6 places) then loses roughly every other batch, a National squad (8) fills exactly, and an Elite squad (10) has two to spare. With a shorter spell the oldest riders would always leave before the next batch arrived and the cap would never matter.
- **Places by level: 6, 8 and 10** for Regional, National and Elite. Only riders in the squad count; graduates do not. A level never drops while the squad is open, so a manager is never over the cap.
- **Graduation frees the place before the next intake is placed**, so a rider leaving and a batch arriving in the same week do not collide.
- **Partial batches.** If a batch of two finds one place, one arrives and one is lost.
- **Promotion at the 30-rider roster cap** is refused; the manager must release or sell someone, or list the graduate instead.
- **The graduate window is two in-season weeks.** Between seasons it does not run, as nothing else does.
- **A promoted rider's salary** is the normal formula value at the moment of promotion, frozen until the next season close like everyone else's.
- **A graduate's market value** is the same valuation as any rider's; listing, bidding, the reserve and resolution are the existing auction rules. AI teams treat a listed graduate like any other listed rider.
- **Discard is permanent and free.** It is also the one exit that nobody else benefits from, so discarding a rider who turns out to be a gem is a plain loss.
- **A squad rider can be promoted before graduating** (the manager has seen enough), at the same salary rule.
- **A rider's slot is not held for them by the squad closing and reopening**: closing discards everyone, reopening starts empty.

## Decisions taken

- **Discard removes the rider from the game**, not to the free-agent pool. Matches the existing treatment of riders who never raced.
- **Graduates released to the pool; squad riders discarded** on close/claim. A rider who has served their spell is a plausible signing; one pulled mid-development is not worth a market place.
- **A fixed spell instead of an age limit.** Easier to read on the screen and independent of where in the age range a rider arrived.
- **Squad cap rises with level (6/8/10)**, so a higher level buys room as well as better odds of a good arrival.
- **A full squad loses the arrivals** rather than displacing a rider. It forces the manager to decide who is worth a place.
- **Development is automatic, varied, and independent of the senior trainer.** Faster developers tend to be the higher-potential ones, which is what makes watching them informative.
- **Graduates can be sold without taking a roster place**, so a manager who does not want a graduate on payroll still gets something for them.
- **Graduate window of two weeks; unsold listings go to the pool.**
- **Spell of 14 weeks**, picked within the 8-14 range the product owner gave, because it is the only value in that range at which the cap binds for the entry level.

## Open questions

- **Tuning, not design:** spell length, caps and window length are all adjustable numbers; the tech plan should keep them in one place. Revisit the 14-week spell after a season of play if Regional squads feel starved.

## Deferred

- **Trainer focus for squad riders** — a balance question about wage-free development; wait to see how fast the automatic development feels.
- **Scout reports on squad riders** — #40.
- **A cap that varies independently of level, or batch-size changes** — wait until the flat 6/8/10 has been played.
- **Notifications for graduation and window expiry** — need a notification system.
