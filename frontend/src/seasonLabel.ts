import type { Position } from './api'

/**
 * `null` means render nothing — a failed fetch or no season declared must
 * never show a fabricated season number (unlike the clock's TEAM.season
 * fallback).
 */
export function seasonLabel(position: Position | null): string | null {
  if (!position) return null
  if (position.state === 'no_season') return null
  if (position.state === 'off_season') return `Season ${position.season} · Off-season`
  return `Season ${position.season} · Week ${position.week}`
}
