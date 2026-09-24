import { useEffect, useState } from 'react'

function pad(n: number): string {
  return String(n).padStart(2, '0')
}

/** Ticks a `deadline` down to `dd hh mm ss`, clamped at zero once it has
 * passed — resolution happens on the next tick, not the instant the
 * countdown reaches zero, so a lingering "00d 00h 00m 00s" is expected
 * and not a bug. */
export function formatCountdown(deadline: string, now: number): string {
  const remainingMs = Math.max(0, new Date(deadline).getTime() - now)
  const totalSeconds = Math.floor(remainingMs / 1000)
  const days = Math.floor(totalSeconds / 86_400)
  const hours = Math.floor((totalSeconds % 86_400) / 3_600)
  const minutes = Math.floor((totalSeconds % 3_600) / 60)
  const seconds = totalSeconds % 60
  return `${pad(days)}d ${pad(hours)}h ${pad(minutes)}m ${pad(seconds)}s`
}

/** A live "dd hh mm ss" countdown to `deadline`, re-rendering every
 * second. One interval per call — fine at the handful of auctions a
 * thin, early market has open at once. */
export function useCountdown(deadline: string): string {
  const [now, setNow] = useState(() => Date.now())

  useEffect(() => {
    const interval = setInterval(() => setNow(Date.now()), 1_000)
    return () => clearInterval(interval)
  }, [])

  return formatCountdown(deadline, now)
}
