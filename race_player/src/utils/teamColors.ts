import type { Rider } from '../types/race'

/**
 * 12-colour palette, validated for perceptual separation (min pairwise
 * CIE76 ΔE 17.7) and white-background contrast (min 3.27:1). Green is
 * avoided (blends into the elevation profile's flat-terrain fill) and pure
 * red is avoided (already means "cracked" elsewhere in the UI). Do not
 * substitute hues without re-checking both properties — see
 * race_player/TEAM_VISUALIZATION_PLAN.md.
 */
export const TEAM_PALETTE: string[] = [
  '#1d56c9', // 1 blue
  '#e26912', // 2 orange
  '#9235d4', // 3 violet
  '#0e9daa', // 4 teal
  '#d0257a', // 5 pink
  '#8a6a0a', // 6 bronze
  '#1089c6', // 7 cyan
  '#a630a6', // 8 magenta
  '#3f6b8f', // 9 steel
  '#bb431b', // 10 rust
  '#7b69d3', // 11 periwinkle
  '#6b7f16', // 12 moss
]

export const NEUTRAL_TEAM_COLOR = '#64748b'

const TEAM_ID_PATTERN = /^t(\d+)$/

function hashToIndex(id: string): number {
  let hash = 0
  for (let i = 0; i < id.length; i++) {
    hash = (hash * 31 + id.charCodeAt(i)) | 0
  }
  return Math.abs(hash) % TEAM_PALETTE.length
}

export function teamColor(team: string | null): string {
  if (team === null) return NEUTRAL_TEAM_COLOR

  const match = TEAM_ID_PATTERN.exec(team)
  if (match) {
    const n = Number(match[1])
    if (n >= 1 && n <= TEAM_PALETTE.length) {
      return TEAM_PALETTE[n - 1]
    }
  }

  return TEAM_PALETTE[hashToIndex(team)]
}

export function isLeader(rider: Rider): boolean {
  return rider.role === 'leader'
}

export function teamCode(teamCodes: Record<string, string>, team: string | null): string {
  if (team === null) return '—'
  return teamCodes[team] ?? '—'
}

export function teamName(teamNames: Record<string, string>, team: string | null): string {
  if (team === null) return '—'
  return teamNames[team] ?? '—'
}
