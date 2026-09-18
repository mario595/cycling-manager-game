/** Total elapsed time: `3h 23m 14s`, dropping the hour under an hour. */
export function formatRaceTime(seconds: number): string {
  const total = Math.floor(seconds)
  const h = Math.floor(total / 3600)
  const m = Math.floor((total % 3600) / 60)
  const s = total % 60
  if (h > 0) return `${h}h ${m}m ${s}s`
  if (m > 0) return `${m}m ${s}s`
  return `${s}s`
}

/** Gap behind the winner: `+0:42`, `+1:02:03` past an hour. Zero is `+0:00`. */
export function formatGap(seconds: number): string {
  const total = Math.floor(seconds)
  const h = Math.floor(total / 3600)
  const m = Math.floor((total % 3600) / 60)
  const s = total % 60
  if (h > 0) return `+${h}:${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`
  return `+${m}:${String(s).padStart(2, '0')}`
}