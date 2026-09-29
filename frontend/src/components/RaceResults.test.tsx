import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { describe, expect, it } from 'vitest'

import type { RaceResults as RaceResultsData } from '../api'
import { GeneralClassificationCard, RiderResultsTable } from './RaceResults'

function withRouter(node: React.ReactElement) {
  return render(<MemoryRouter>{node}</MemoryRouter>)
}

const oneDayResults: RaceResultsData = {
  race: { id: 1, name: 'Opening Classic', status: 'finished', stage_race: null },
  results: [
    {
      position: 1, rider: { id: 1, name: 'Winner' },
      team: { id: 1, name: 'Team A', code: 'ALP' },
      finish_time: 3600, group_time: 3595, finished: true,
    },
    {
      position: 2, rider: { id: 2, name: 'Runner Up' },
      team: { id: 2, name: 'Team B', code: 'BET' },
      finish_time: 3610, group_time: 3595, finished: true,
    },
  ],
  points: [],
  markers: [],
  gc: null,
}

const stageResults: RaceResultsData = {
  race: {
    id: 2, name: 'Alpine Tour — Stage 1', status: 'finished',
    stage_race: { id: 7, name: 'Alpine Tour', stage_number: 1, stage_count: 3 },
  },
  results: [
    {
      position: 1, rider: { id: 1, name: 'Winner' },
      team: { id: 1, name: 'Team A', code: 'ALP' },
      finish_time: 3600, group_time: 3595, finished: true,
    },
    {
      position: 2, rider: { id: 2, name: 'Runner Up' },
      team: { id: 2, name: 'Team B', code: 'BET' },
      finish_time: 3610, group_time: 3595, finished: true,
    },
  ],
  points: [],
  markers: [],
  gc: {
    after_stage: 1,
    final: false,
    standings: [
      { position: 1, rider: { id: 1, name: 'Winner' }, team: { id: 1, name: 'Team A', code: 'ALP' }, gc_time: 3595, gap: 0 },
    ],
    points: [],
  },
}

describe('RiderResultsTable', () => {
  it('one-day gaps use finish_time', () => {
    withRouter(<RiderResultsTable results={oneDayResults} payout={[]} />)

    // finish_time gap is 3610-3600=10s -> +0:10; group_time (both 3595)
    // would show +0:00, so this pins the one-day race reads finish_time.
    expect(screen.getByText('+0:10')).toBeInTheDocument()
  })

  it('stage gaps use group_time', () => {
    withRouter(<RiderResultsTable results={stageResults} payout={[]} />)

    // Both riders share group_time 3595, so the gap must read +0:00 even
    // though their finish_time differs by 10 seconds.
    expect(screen.getByText('+0:00')).toBeInTheDocument()
    expect(screen.queryByText('+0:10')).not.toBeInTheDocument()
  })
})

describe('GeneralClassificationCard', () => {
  it('renders final GC with points and prizes', () => {
    const finalResults: RaceResultsData = {
      ...stageResults,
      gc: {
        after_stage: 3,
        final: true,
        standings: [
          { position: 1, rider: { id: 1, name: 'Winner' }, team: { id: 1, name: 'Team A', code: 'ALP' }, gc_time: 10000, gap: 0 },
          { position: 2, rider: { id: 2, name: 'Runner Up' }, team: { id: 2, name: 'Team B', code: 'BET' }, gc_time: 10042, gap: 42 },
        ],
        points: [
          { team: { id: 1, name: 'Team A', code: 'ALP' }, position: 1, points: 40, prize: 40_000 },
        ],
      },
    }

    withRouter(<GeneralClassificationCard results={finalResults} />)

    expect(screen.getByText('Final general classification')).toBeInTheDocument()
    expect(screen.getByText('+0:42')).toBeInTheDocument()
    expect(screen.getByText('$40,000')).toBeInTheDocument()
    expect(screen.getByText('40')).toBeInTheDocument()
  })

  it('shows the stage number, not final, before the tour completes', () => {
    withRouter(<GeneralClassificationCard results={stageResults} />)

    expect(screen.getByText('General classification after stage 1')).toBeInTheDocument()
  })
})
