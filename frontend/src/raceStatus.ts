import type { CalendarRace } from './api'
import { color } from './theme'

/**
 * `failed` is a real tick outcome (a simulation that threw) that the
 * calendar spec never anticipated. Folding it into "finished" would show a
 * player a completed race with no result, so it gets its own honest word.
 */
export function raceStatusLabel(status: CalendarRace['status']): string {
  switch (status) {
    case 'scheduled':
      return 'Upcoming'
    case 'running':
      return 'Racing now'
    case 'finished':
      return 'Result in'
    case 'failed':
      return 'Not run'
  }
}

export function raceStatusTone(status: CalendarRace['status']): string {
  switch (status) {
    case 'scheduled':
      return color.muted
    case 'running':
      return color.accent
    case 'finished':
      return color.positive
    case 'failed':
      return color.negative
  }
}
