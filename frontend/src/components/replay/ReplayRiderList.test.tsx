import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import type { Pack, Rider } from '../../../../race_player/src/types/race'

import { ReplayRiderList } from './ReplayRiderList'

function rider(id: string, overrides: Partial<Rider> = {}): Rider {
  return {
    id,
    name: id,
    team: '7',
    role: 'support',
    pos: 1000,
    speed: 10,
    energy: 80,
    stamina: 70,
    pulling: false,
    surging: false,
    finished: false,
    dnf: false,
    finish_time: null,
    ...overrides,
  }
}

function pack(riders: Rider[]): Pack {
  return { riders, frontPos: riders[0].pos, speed: riders[0].speed }
}

const teams = { '7': 'ALP', '9': 'TDE' }
const names = { '7': 'Alpine Racing', '9': 'Team Nine' }

function renderList(packs: Pack[], highlightTeam: string | null = null, out: Rider[] = []) {
  return render(
    <ReplayRiderList
      packs={packs}
      out={out}
      teamCodes={teams}
      teamNames={names}
      results={new Map()}
      highlightTeam={highlightTeam}
    />,
  )
}

describe('ReplayRiderList', () => {
  it('prints the gap between two packs', () => {
    // 500 m behind at 10 m/s: 50 s, and the metres are the ones actually
    // covered between the packs.
    renderList([pack([rider('leader')]), pack([rider('chaser', { pos: 500 })])])

    expect(screen.getByText('+50s · 500 m')).toBeInTheDocument()
  })

  it('prints no gap above the leading pack', () => {
    renderList([pack([rider('leader')])])

    expect(screen.queryByText(/·\s*\d+ m/)).toBeNull()
  })

  it('marks the team leader', () => {
    renderList([pack([rider('boss', { role: 'leader' }), rider('helper')])])

    // Only the leader's row carries one; the legend's own star has no title.
    expect(screen.getAllByTitle('Team leader')).toHaveLength(1)
  })

  it('tags a rider on the front and one attacking', () => {
    renderList([pack([rider('front', { pulling: true }), rider('attacker', { surging: true })])])

    expect(screen.getByText('PULL')).toBeInTheDocument()
    expect(screen.getByText('ATK')).toBeInTheDocument()
  })

  it('tints the player own riders and only theirs', () => {
    renderList(
      [pack([rider('mine', { team: '7' }), rider('theirs', { team: '9' })])],
      '7',
    )

    expect(screen.getByText('mine').closest('[data-own-team]')).toHaveAttribute('data-own-team', 'true')
    expect(screen.getByText('theirs').closest('[data-own-team]')).toBeNull()
  })

  it('shows the out block after the last pack', () => {
    renderList([pack([rider('still racing')])], null, [rider('gone', { dnf: true })])

    expect(screen.getByText('Out of the race')).toBeInTheDocument()
    // A time-cut rider has no rank on the road.
    expect(screen.getByText('DNF')).toBeInTheDocument()
  })

  it('prints the legend', () => {
    renderList([pack([rider('rider one')])])

    expect(screen.getByText('PULL on the front')).toBeInTheDocument()
    expect(screen.getByText('ATK attacking')).toBeInTheDocument()
  })
})
