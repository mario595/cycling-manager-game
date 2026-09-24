import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import type { AttributeSnapshot } from '../api'
import { AttributeHistoryChart, historySeries } from './AttributeHistoryChart'

const CURRENT = { climb: 9, sprint: 4, flat: 5, resistance: 6, positioning: 5 }

function baseline(values: Partial<typeof CURRENT> = {}): AttributeSnapshot {
  return { season: null, week: null, climb: 7, sprint: 3, flat: 4, resistance: 6, positioning: 5, ...values }
}

function weekly(season: number, week: number, values: Partial<typeof CURRENT> = {}): AttributeSnapshot {
  return { season, week, climb: 8, sprint: 3, flat: 4, resistance: 6, positioning: 5, ...values }
}

describe('historySeries', () => {
  it('places the baseline one unit before the current week when there are no weekly snapshots', () => {
    const { points } = historySeries([baseline()], CURRENT, { season: 1, week: 5 })

    expect(points).toHaveLength(2)
    expect(points[0]).toMatchObject({ x: 4, label: 'Start' })
    expect(points[1]).toMatchObject({ x: 5, label: 'S1 W5' })
  })

  it('places weekly snapshots on the season-week axis, then the current point', () => {
    const history = [baseline(), weekly(1, 3), weekly(2, 1)]

    const { points } = historySeries(history, CURRENT, { season: 2, week: 2 })

    expect(points.map((p) => p.x)).toEqual([2, 3, 13, 14])
  })

  it('carries the current attribute values on the final point, even when they differ from the last snapshot', () => {
    const history = [baseline(), weekly(1, 3, { climb: 8 })]

    const { points } = historySeries(history, CURRENT, { season: 1, week: 6 })

    expect(points[points.length - 1].values).toEqual(CURRENT)
  })

  it('places the baseline at 0 when there is no current week', () => {
    const { points } = historySeries([baseline()], CURRENT, null)

    expect(points[0]).toMatchObject({ x: 0, label: 'Start' })
  })
})

describe('AttributeHistoryChart', () => {
  it('shows the "no change yet" caption for baseline-only history', () => {
    render(
      <AttributeHistoryChart history={[baseline()]} current={CURRENT} currentWeek={{ season: 1, week: 5 }} />,
    )

    expect(
      screen.getByText("Recording began at the start of this rider's history; no change yet."),
    ).toBeInTheDocument()
  })

  it('does not show the caption once a weekly snapshot exists', () => {
    render(
      <AttributeHistoryChart
        history={[baseline(), weekly(1, 3)]}
        current={CURRENT}
        currentWeek={{ season: 1, week: 5 }}
      />,
    )

    expect(
      screen.queryByText("Recording began at the start of this rider's history; no change yet."),
    ).not.toBeInTheDocument()
  })
})
