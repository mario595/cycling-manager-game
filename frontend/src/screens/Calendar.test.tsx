import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { describe, expect, it, vi } from 'vitest'

import type { Calendar as CalendarData, CalendarRace } from '../api'
import { useCalendar } from '../useCalendar'
import { Calendar } from './Calendar'

vi.mock('../useCalendar', () => ({ useCalendar: vi.fn() }))

const mockUseCalendar = vi.mocked(useCalendar)

function oneDayRace(overrides: Partial<CalendarRace> = {}): CalendarRace {
  return {
    id: 1,
    name: 'Opening Classic',
    starts_at: '2027-03-07T14:00:00Z',
    status: 'scheduled',
    distance_km: 180,
    stage_race: null,
    ...overrides,
  }
}

function stageOf(stageNumber: number, dayOffset: number): CalendarRace {
  return {
    id: 100 + stageNumber,
    name: `Alpine Tour — Stage ${stageNumber}`,
    starts_at: `2027-03-0${1 + dayOffset}T14:00:00Z`,
    status: 'scheduled',
    distance_km: 130,
    stage_race: { id: 7, name: 'Alpine Tour', stage_number: stageNumber, stage_count: 3 },
  }
}

function calendarWith(races: CalendarRace[]): CalendarData {
  return {
    state: 'in_season',
    season: 1,
    current_week: 1,
    weeks: [
      { number: 1, starts_at: '2027-03-01T00:00:00Z', races },
      ...Array.from({ length: 11 }, (_, i) => ({
        number: i + 2,
        starts_at: '2027-03-08T00:00:00Z',
        races: [] as CalendarRace[],
      })),
    ],
  }
}

function renderCalendar() {
  return render(
    <MemoryRouter>
      <Calendar />
    </MemoryRouter>,
  )
}

describe('Calendar', () => {
  it('groups stages of a stage race under one header', () => {
    mockUseCalendar.mockReturnValue({
      calendar: calendarWith([stageOf(1, 0), stageOf(2, 1), stageOf(3, 2)]),
      loading: false,
      error: false,
    })

    renderCalendar()

    expect(screen.getByText('Alpine Tour')).toBeInTheDocument()
    expect(screen.getByText('3 stages · Mon–Wed')).toBeInTheDocument()
    expect(screen.getByText('Stage 1')).toBeInTheDocument()
    expect(screen.getByText('Stage 2')).toBeInTheDocument()
    expect(screen.getByText('Stage 3')).toBeInTheDocument()
    // The stages' own names never render — the stage label replaces them.
    expect(screen.queryByText('Alpine Tour — Stage 1')).not.toBeInTheDocument()
  })

  it('renders one-day races unchanged', () => {
    mockUseCalendar.mockReturnValue({
      calendar: calendarWith([oneDayRace()]),
      loading: false,
      error: false,
    })

    renderCalendar()

    expect(screen.getByText('Opening Classic')).toBeInTheDocument()
    expect(screen.queryByText(/stages/)).not.toBeInTheDocument()
  })
})
