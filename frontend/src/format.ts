/** The game's abstract currency — see AGENTS.md, *Displaying game money*.
 * Thousands-separated, never decimals, prefixed "$" so it reads as money at
 * a glance and is never mistaken for a fan count. The sign goes before the
 * "$" (e.g. "−$12,400"), not between it and the digits. */
export function formatMoney(amount: number): string {
  const sign = amount < 0 ? '−' : ''
  return `${sign}$${Math.abs(amount).toLocaleString('en-US')}`
}

/** Dates are always day-first (#153). Every date the SPA shows goes through
 * the helpers below, which pin this locale rather than the browser's, so an
 * en-US browser no longer renders `11/25/2026` or `Nov 25`. */
export const DATE_LOCALE = 'en-GB'

type DateInput = Date | string

function toDate(value: DateInput): Date {
  return typeof value === 'string' ? new Date(value) : value
}

/** A numeric calendar date: `25/11/2026`. */
export function formatDate(value: DateInput): string {
  return toDate(value).toLocaleDateString(DATE_LOCALE, { day: '2-digit', month: '2-digit', year: 'numeric' })
}

/** Day and short month, day first: `25 Nov`. */
export function formatShortDate(value: DateInput): string {
  return toDate(value).toLocaleDateString(DATE_LOCALE, { day: 'numeric', month: 'short' })
}

/** Short month name alone: `Nov`. */
export function formatMonth(value: DateInput): string {
  return toDate(value).toLocaleDateString(DATE_LOCALE, { month: 'short' })
}

/** Short weekday alone: `Wed`. */
export function formatWeekday(value: DateInput): string {
  return toDate(value).toLocaleDateString(DATE_LOCALE, { weekday: 'short' })
}
