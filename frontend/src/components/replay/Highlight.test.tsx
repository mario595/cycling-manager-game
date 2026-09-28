import { render } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import ElevationProfile from '../../../../race_player/src/components/ElevationProfile'
import { computeProfile } from '../../../../race_player/src/utils/profile'
import type { Pack, Rider } from '../../../../race_player/src/types/race'

function rider(id: string, team: string, pos: number): Rider {
  return {
    id,
    name: id,
    team,
    role: 'support',
    pos,
    speed: 10,
    energy: 80,
    stamina: 70,
    pulling: false,
    surging: false,
    finished: false,
    dnf: false,
    finish_time: null,
  }
}

function pack(riders: Rider[]): Pack {
  return {
    riders,
    frontPos: riders[0].pos,
    speed: riders[0].speed,
  }
}

const PROFILE = computeProfile([{ length: 10000, gradient: 0 }])

describe('ElevationProfile own-team highlight', () => {
  it('rings only the markers of the highlighted team', () => {
    // Two far-apart single-rider packs, so neither becomes a pack blob.
    const packs = [
      pack([rider('mine', '7', 5000)]),
      pack([rider('theirs', '9', 1000)]),
    ]

    const { container } = render(
      <ElevationProfile
        profile={PROFILE}
        packs={packs}
        highlightTeam="7"
        highlightColor="#123456"
      />,
    )

    const rings = container.querySelectorAll('circle[stroke="#123456"]')
    expect(rings).toHaveLength(1)
    expect(rings[0].getAttribute('r')).toBe('8.5')
  })

  it('rings nothing when no team is highlighted', () => {
    const packs = [pack([rider('mine', '7', 5000)])]

    const { container } = render(<ElevationProfile profile={PROFILE} packs={packs} />)

    expect(container.querySelectorAll('circle[stroke="#0f172a"]')).toHaveLength(0)
  })
})
