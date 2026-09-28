import { describe, expect, it } from 'vitest'

import { packGaps } from './packGaps'
import type { Pack, Rider } from '../types/race'

function rider(id: string, pos: number): Rider {
  return {
    id,
    name: id,
    team: 't1',
    role: 'support',
    pos,
    speed: 10,
    energy: 90,
    stamina: 90,
    pulling: false,
    surging: false,
    finished: false,
    dnf: false,
    finish_time: null,
  }
}

function pack(ids: string[], frontPos: number, speed: number): Pack {
  return { riders: ids.map((id, i) => rider(id, frontPos - i * 10)), frontPos, speed }
}

describe('packGaps', () => {
  it('has no gap ahead of the leading pack', () => {
    expect(packGaps([pack(['a'], 100, 10)])).toEqual([null])
  })

  it('measures the gap from each pack back to the one ahead', () => {
    const gaps = packGaps([pack(['a'], 100, 10), pack(['b', 'c'], 40, 10)])

    // The trailing pack's front sits at 40, the leaders at 100, and it is
    // moving at 10 m/s.
    expect(gaps[1]).toEqual({ meters: 60, seconds: 6 })
  })

  it('reports zero seconds for a pack that is not moving', () => {
    const gaps = packGaps([pack(['a'], 100, 10), pack(['b'], 50, 0)])

    expect(gaps[1]).toEqual({ meters: 50, seconds: 0 })
  })
})
