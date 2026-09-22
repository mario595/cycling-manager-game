/** The game's abstract currency — see AGENTS.md, *Displaying game money*.
 * Thousands-separated, never decimals, prefixed "$" so it reads as money at
 * a glance and is never mistaken for a fan count. The sign goes before the
 * "$" (e.g. "−$12,400"), not between it and the digits. */
export function formatMoney(amount: number): string {
  const sign = amount < 0 ? '−' : ''
  return `${sign}$${Math.abs(amount).toLocaleString('en-US')}`
}
