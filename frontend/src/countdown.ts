function pad(n: number): string {
  return String(n).padStart(2, '0')
}

/** Formats a `dd hh mm ss` countdown from `now` (epoch ms) to `deadline`,
 * clamped at zero once it has passed — resolution happens on the next
 * tick, not the instant the countdown reaches zero, so a lingering
 * "00d 00h 00m 00s" is expected and not a bug.
 *
 * `now` must be **game** time, not the browser's wall clock: `deadline`
 * is a game-time value (`world.services.now()`), and under `MockClock` —
 * the mode the game runs in whenever a developer is exercising auctions
 * by hand (AGENTS.md) — the two can differ by days. Callers get game
 * time from `useClock()` and pass its `now` in; see `AuctionCard`.
 */
export function formatCountdown(deadline: string, now: number): string {
  const remainingMs = Math.max(0, new Date(deadline).getTime() - now)
  const totalSeconds = Math.floor(remainingMs / 1000)
  const days = Math.floor(totalSeconds / 86_400)
  const hours = Math.floor((totalSeconds % 86_400) / 3_600)
  const minutes = Math.floor((totalSeconds % 3_600) / 60)
  const seconds = totalSeconds % 60
  return `${pad(days)}d ${pad(hours)}h ${pad(minutes)}m ${pad(seconds)}s`
}
