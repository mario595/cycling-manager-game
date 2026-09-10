export function formatGapTime(gapSeconds: number): string {
  const total = Math.round(gapSeconds)
  const minutes = Math.floor(total / 60)
  const seconds = total % 60
  return minutes > 0 ? `${minutes}m ${seconds}s` : `${seconds}s`
}

export function formatFinishTime(seconds: number): string {
  const total = Math.round(seconds)
  const hours = Math.floor(total / 3600)
  const minutes = Math.floor((total % 3600) / 60)
  const secs = total % 60
  return [hours, minutes, secs].map((n) => String(n).padStart(2, '0')).join(':')
}
