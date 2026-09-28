import type { Pack } from '../types/race'

export interface PackGap {
  seconds: number
  meters: number
}

/** Gap from each pack to the one ahead; null for the leading pack. Shared
 * with the game's replay screen, which formats the same two numbers
 * differently. */
export function packGaps(packs: Pack[]): (PackGap | null)[] {
  return packs.map((pack, i) => {
    if (i === 0) return null
    const ahead = packs[i - 1]
    const aheadBack = ahead.riders[ahead.riders.length - 1].pos
    const meters = Math.max(0, aheadBack - pack.frontPos)
    return { seconds: pack.speed > 0 ? meters / pack.speed : 0, meters }
  })
}
