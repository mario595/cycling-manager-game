import type { Pack, ProfilePoint, Rider } from '../types/race'

const PACK_COHESION_DISTANCE = 60.0
const DRAFT_UPHILL_LIMIT = 5.0

function gradientAtDistance(profile: ProfilePoint[], pos: number): number {
  if (pos <= 0) return profile[0]?.gradient ?? 0

  const last = profile[profile.length - 1]
  if (pos >= last.distance) return last.gradient

  let lo = 0
  let hi = profile.length - 1
  while (hi - lo > 1) {
    const mid = (lo + hi) >> 1
    if (profile[mid].distance <= pos) {
      lo = mid
    } else {
      hi = mid
    }
  }

  const p1 = profile[lo]
  const p2 = profile[hi]
  const t = p2.distance === p1.distance ? 0 : (pos - p1.distance) / (p2.distance - p1.distance)
  return p1.gradient + t * (p2.gradient - p1.gradient)
}

/**
 * Groups riders into packs mirroring the race engine: undirected adjacency
 * when two riders on draft-allowed terrain sit within PACK_COHESION_DISTANCE
 * of each other, unioned via BFS. A single rider is its own pack.
 */
// Once multiple riders finish they all sit at the same `pos` (course_length),
// so ranking by pos alone leaves ties in arbitrary array order. Break ties by
// finish_time ascending (earlier finisher ranks first) — this is the only
// thing that still distinguishes finished riders from one another.
function comparePosition(a: Rider, b: Rider): number {
  if (b.pos !== a.pos) return b.pos - a.pos
  if (a.finished && b.finished) return (a.finish_time ?? 0) - (b.finish_time ?? 0)
  return 0
}

export function computePacks(riders: Rider[], profile: ProfilePoint[]): Pack[] {
  if (riders.length === 0) return []

  const sorted = [...riders].sort(comparePosition)

  const idxOf = new Map(sorted.map((r, i) => [i, r]))
  const n = sorted.length

  const adj: number[][] = Array.from({ length: n }, () => [])
  for (let i = 0; i < n; i++) {
    const rider = idxOf.get(i)!
    const gradient = gradientAtDistance(profile, rider.pos)
    if (gradient > DRAFT_UPHILL_LIMIT) continue
    for (let j = 0; j < n; j++) {
      if (i === j) continue
      const other = idxOf.get(j)!
      if (other.pos < rider.pos) continue
      if (other.pos - rider.pos > PACK_COHESION_DISTANCE) break
      const g = gradientAtDistance(profile, other.pos)
      if (g > DRAFT_UPHILL_LIMIT) continue
      adj[i].push(j)
      adj[j].push(i)
    }
  }

  const packs: Pack[] = []
  const seen = new Set<number>()
  for (let start = 0; start < n; start++) {
    if (seen.has(start)) continue
    const comp: number[] = []
    const stack = [start]
    seen.add(start)
    while (stack.length) {
      const cur = stack.pop()!
      comp.push(cur)
      for (const nb of adj[cur]) {
        if (!seen.has(nb)) {
          seen.add(nb)
          stack.push(nb)
        }
      }
    }
    const members = comp
      .map((k) => idxOf.get(k)!)
      .sort(comparePosition)
    const front = members[0]
    packs.push({ riders: members, frontPos: front.pos, speed: front.speed })
  }

  packs.sort((a, b) => b.frontPos - a.frontPos)

  return packs
}
