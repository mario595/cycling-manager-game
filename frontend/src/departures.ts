import type { Departure, DevelopmentSquadGraduate, Position } from './api'
import { formatMoney } from './format'

/** How far back the dashboard looks: two game weeks (#158, spec item 4). */
export const RECENT_DEPARTURE_MS = 14 * 24 * 60 * 60 * 1000

/** "Season 4, Week 6", "Season 3" between seasons, or null outside any. */
export function weekLabel(season: number | null, week: number | null): string | null {
  if (season === null) return null
  return week === null ? `Season ${season}` : `Season ${season}, Week ${week}`
}

/** What happened, after the rider's name: one sentence fragment per kind.
 * A retirement is dated to the closing season's last week, so it reads as
 * "at the end of Season N" rather than naming week 12. */
export function departureText(departure: Departure): string {
  const when = weekLabel(departure.season, departure.week)
  switch (departure.kind) {
    case 'retired':
      return departure.season === null
        ? 'retired'
        : `retired at the end of Season ${departure.season}`
    case 'released':
      return when
        ? `was released to the free agents in ${when}`
        : 'was released to the free agents'
    case 'sold': {
      const buyer = departure.buyer ? ` to ${departure.buyer.name}` : ''
      const fee = departure.fee !== null ? ` for ${formatMoney(departure.fee)}` : ''
      return `was sold${buyer}${fee}${when ? ` in ${when}` : ''}`
    }
  }
}

/** Within the last two game weeks of `now` (game time). */
export function isRecent(departure: Departure, now: Date): boolean {
  return now.getTime() - new Date(departure.at).getTime() < RECENT_DEPARTURE_MS
}

/** The roster screen's window (spec item 5): everything this season, plus
 * the retirements at the last close, which are dated to the previous
 * season's final week. Off-season, the season that just finished counts as
 * "this season". */
export function thisSeasonsDepartures(departures: Departure[], position: Position | null): Departure[] {
  const current = position?.season ?? null
  if (current === null) return []
  return departures.filter(
    (d) => d.season === current || (d.kind === 'retired' && d.season === current - 1),
  )
}

/** True in the last two weeks of a season (spec item 10). */
export function inFinalWeeks(position: Position | null): boolean {
  if (!position || position.state !== 'in_season' || position.week === null) return false
  return position.week >= position.weeks_in_season - 1
}

/** "Decide before Season 4, Week 6 (2 weeks left)", or just the count when
 * that week is not in the calendar yet (#162). The named week is the one at
 * whose start the release happens, so the whole of the week before is still
 * the manager's. */
export function graduateDeadline(rider: DevelopmentSquadGraduate): string {
  const left = `${rider.weeks_left} week${rider.weeks_left === 1 ? '' : 's'} left`
  const due = rider.decision_due ? weekLabel(rider.decision_due.season, rider.decision_due.week) : null
  return due ? `Decide before ${due} (${left})` : `Decide within ${left.replace(' left', '')}`
}
