import type { Calendar, CalendarRace } from './api'

function raceStartValue(race: CalendarRace): string {
  // A null starts_at is a race with no declared time; never treat it as
  // before a dated race.
  return race.starts_at ?? '\uffff'
}

/**
 * The next race a manager must act on: the first on the calendar, in week
 * order and starts_at order within a week, whose status is not `finished`
 * and not `failed`. A `running` race is still next — it is the one being
 * resolved right now. `failed` is skipped because it will never produce a
 * result. Returns null when the calendar is null or every race is over.
 */
export function nextRace(calendar: Calendar | null): CalendarRace | null {
  if (!calendar) return null

  for (const week of calendar.weeks) {
    const pending = week.races
      .filter((race) => race.status !== 'finished' && race.status !== 'failed')
      .sort((a, b) => raceStartValue(a).localeCompare(raceStartValue(b)))
    if (pending.length > 0) return pending[0]
  }
  return null
}