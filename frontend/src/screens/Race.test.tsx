import { fireEvent, render, screen } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import type { RaceDetail, RaceMarker, RaceResults, Squad } from '../api'
import { useRaceDetail } from '../useRaceDetail'
import { useRaceResults } from '../useRaceResults'
import { useSquad } from '../useSquad'
import { Race } from './Race'

vi.mock('../useRaceDetail', () => ({ useRaceDetail: vi.fn() }))
vi.mock('../useRaceResults', () => ({ useRaceResults: vi.fn() }))
vi.mock('../useSquad', () => ({ useSquad: vi.fn() }))

const mockUseRaceDetail = vi.mocked(useRaceDetail)
const mockUseRaceResults = vi.mocked(useRaceResults)
const mockUseSquad = vi.mocked(useSquad)

const upcomingRace: RaceDetail = {
  id: 42,
  name: 'Circuit of Example',
  status: 'scheduled',
  starts_at: '2027-03-15T10:00:00Z',
  distance_km: 50,
  course: [
    { length: 40000, gradient: 0.02 },
    { length: 10000, gradient: 0 },
  ],
  payout: [
    { position: 1, points: 20, prize: 20_000 },
    { position: 2, points: 15, prize: 15_000 },
    { position: 3, points: 12, prize: 12_000 },
    { position: 10, points: 1, prize: 1_000 },
  ],
  gc_payout: [],
  markers: [],
  has_replay: false,
  stage_race: null,
}

const finishedResults: RaceResults = {
  race: { id: 42, name: 'Circuit of Example', status: 'finished', stage_race: null },
  results: [
    {
      position: 1,
      rider: { id: 1, name: 'Winner Rider' },
      team: { id: 1, name: 'Results Team', code: 'RES' },
      finish_time: 3600,
      group_time: 3600,
      finished: true,
    },
    {
      position: 2,
      rider: { id: 2, name: 'Second Rider' },
      team: { id: 1, name: 'Results Team', code: 'RES' },
      finish_time: 3642,
      group_time: 3642,
      finished: true,
    },
    // A rider who abandons keeps a position but never finishes, so must not
    // draw a prize even when that position pays one (see racing/services.py).
    {
      position: 3,
      rider: { id: 3, name: 'DNF Rider' },
      team: { id: 2, name: 'Zero Team', code: 'ZRO' },
      finish_time: null,
      group_time: null,
      finished: false,
    },
  ],
  points: [
    // Two placed riders in the same team: the API's points row carries the
    // summed prize (35_000), but the SPA must not render it at the team
    // level — the winnings live with the riders who earned them.
    { team: { id: 1, name: 'Results Team', code: 'RES' }, position: 1, points: 20, prize: 35_000 },
    { team: { id: 2, name: 'Zero Team', code: 'ZRO' }, position: null, points: 0, prize: 0 },
  ],
  markers: [],
  gc: null,
}

const markers: RaceMarker[] = [
  { id: 1, kind: 'sprint', name: 'Line One', distance: 40000 },
  { id: 2, kind: 'mountain', name: 'Summit', distance: 80000 },
]

const finishedResultsWithMarkers: RaceResults = {
  ...finishedResults,
  markers: [
    {
      id: 1,
      kind: 'sprint',
      name: 'Line One',
      distance: 40000,
      crossings: [
        { position: 1, rider: { id: 1, name: 'Winner Rider' }, team: { id: 1, name: 'Results Team', code: 'RES' } },
        { position: 2, rider: { id: 2, name: 'Second Rider' }, team: { id: 1, name: 'Results Team', code: 'RES' } },
        { position: 3, rider: { id: 3, name: 'DNF Rider' }, team: { id: 2, name: 'Zero Team', code: 'ZRO' } },
      ],
    },
  ],
}

const squad: Squad = {
  race: 42,
  race_name: 'Circuit of Example',
  race_status: 'scheduled',
  starts_at: '2027-03-15T10:00:00Z',
  distance_km: 50,
  team: 1,
  team_name: 'Squad Team',
  editable: true,
  saved: false,
  squad_size: 4,
  candidates: [
    { id: 1, name: 'Rider One', speciality: 'Climber', age: 25, climb: 8, sprint: 5, flat: 6, resistance: 7, positioning: 6, freshness: 8, selected: true, is_leader: true },
    { id: 2, name: 'Rider Two', speciality: 'Sprinter', age: 26, climb: 4, sprint: 9, flat: 8, resistance: 6, positioning: 7, freshness: 7, selected: true, is_leader: false },
    { id: 3, name: 'Rider Three', speciality: 'Puncher', age: 27, climb: 6, sprint: 6, flat: 6, resistance: 6, positioning: 6, freshness: 7, selected: true, is_leader: false },
    { id: 4, name: 'Rider Four', speciality: 'Time trialist', age: 28, climb: 5, sprint: 5, flat: 5, resistance: 8, positioning: 5, freshness: 6, selected: true, is_leader: false },
  ],
  stage_race: null,
}

function renderRace() {
  return render(
    <MemoryRouter initialEntries={['/race/42']}>
      <Routes>
        <Route path="/race/:raceId" element={<Race />} />
      </Routes>
    </MemoryRouter>,
  )
}

/** A finished race's tables are behind a reveal, so every test that wants
 * them has to ask. */
function revealResults() {
  fireEvent.click(screen.getByRole('button', { name: 'Show results' }))
}

function noSquad() {
  mockUseSquad.mockReturnValue({
    squad: null,
    loading: false,
    error: false,
    save: vi.fn(),
    saving: false,
    saveError: null,
  })
}

beforeEach(() => {
  noSquad()
})

describe('Race', () => {
  it('renders the course profile for an upcoming race', () => {
    mockUseRaceDetail.mockReturnValue({ race: upcomingRace, loading: false, error: false })
    mockUseRaceResults.mockReturnValue({ results: null, loading: false, error: false })
    mockUseSquad.mockReturnValue({
      squad,
      loading: false,
      error: false,
      save: vi.fn(),
      saving: false,
      saveError: null,
    })

    const { container } = renderRace()

    expect(screen.getByText('Circuit of Example')).toBeInTheDocument()
    expect(container.querySelector('svg[aria-label="Elevation profile"]')).not.toBeNull()
  })

  it('renders the payout table for an upcoming race', () => {
    mockUseRaceDetail.mockReturnValue({ race: upcomingRace, loading: false, error: false })
    mockUseRaceResults.mockReturnValue({ results: null, loading: false, error: false })
    mockUseSquad.mockReturnValue({
      squad,
      loading: false,
      error: false,
      save: vi.fn(),
      saving: false,
      saveError: null,
    })

    renderRace()

    expect(screen.getByText('Prize list')).toBeInTheDocument()
    expect(screen.getByText('$20,000')).toBeInTheDocument()
    expect(screen.getByText('$1,000')).toBeInTheDocument()
  })

  it('shows stage strip and GC payout', () => {
    const stageRace: RaceDetail = {
      ...upcomingRace,
      gc_payout: [
        { position: 1, points: 40, prize: 40_000 },
        { position: 2, points: 30, prize: 30_000 },
      ],
      stage_race: {
        id: 7,
        name: 'Alpine Tour',
        stage_number: 1,
        stage_count: 2,
        stages: [
          { id: 42, stage_number: 1, starts_at: '2027-03-15T10:00:00Z', status: 'scheduled' },
          { id: 43, stage_number: 2, starts_at: '2027-03-16T10:00:00Z', status: 'scheduled' },
        ],
      },
    }
    mockUseRaceDetail.mockReturnValue({ race: stageRace, loading: false, error: false })
    mockUseRaceResults.mockReturnValue({ results: null, loading: false, error: false })
    mockUseSquad.mockReturnValue({
      squad,
      loading: false,
      error: false,
      save: vi.fn(),
      saving: false,
      saveError: null,
    })

    renderRace()

    expect(screen.getByText('Stage 1 of 2 — Alpine Tour')).toBeInTheDocument()
    expect(screen.getByText('Stage prize list')).toBeInTheDocument()
    expect(screen.getByText('General classification')).toBeInTheDocument()
    expect(screen.getByText('$40,000')).toBeInTheDocument()
  })

  it('squad note on stage 1', () => {
    const stageRace: RaceDetail = {
      ...upcomingRace,
      stage_race: {
        id: 7, name: 'Alpine Tour', stage_number: 1, stage_count: 2,
        stages: [
          { id: 42, stage_number: 1, starts_at: '2027-03-15T10:00:00Z', status: 'scheduled' },
          { id: 43, stage_number: 2, starts_at: '2027-03-16T10:00:00Z', status: 'scheduled' },
        ],
      },
    }
    mockUseRaceDetail.mockReturnValue({ race: stageRace, loading: false, error: false })
    mockUseRaceResults.mockReturnValue({ results: null, loading: false, error: false })
    mockUseSquad.mockReturnValue({
      squad: { ...squad, stage_race: { name: 'Alpine Tour', stage_number: 1 } },
      loading: false,
      error: false,
      save: vi.fn(),
      saving: false,
      saveError: null,
    })

    renderRace()

    expect(screen.getByText('This squad and leader ride every stage of Alpine Tour.')).toBeInTheDocument()
  })

  it('later stage squad is read-only', () => {
    const stageRace: RaceDetail = {
      ...upcomingRace,
      id: 43,
      stage_race: {
        id: 7, name: 'Alpine Tour', stage_number: 2, stage_count: 2,
        stages: [
          { id: 42, stage_number: 1, starts_at: '2027-03-15T10:00:00Z', status: 'finished' },
          { id: 43, stage_number: 2, starts_at: '2027-03-16T10:00:00Z', status: 'scheduled' },
        ],
      },
    }
    mockUseRaceDetail.mockReturnValue({ race: stageRace, loading: false, error: false })
    mockUseRaceResults.mockReturnValue({ results: null, loading: false, error: false })
    mockUseSquad.mockReturnValue({
      squad: { ...squad, editable: false, stage_race: { name: 'Alpine Tour', stage_number: 2 } },
      loading: false,
      error: false,
      save: vi.fn(),
      saving: false,
      saveError: null,
    })

    renderRace()

    expect(screen.getByText("Chosen at stage 1 — riders who didn't finish an earlier stage are out.")).toBeInTheDocument()
    expect(screen.getByText('Squad')).toBeInTheDocument()
    expect(screen.queryByText('Confirm squad')).not.toBeInTheDocument()
  })

  it('renders the course profile and both tables for a finished race', () => {
    mockUseRaceDetail.mockReturnValue({
      race: { ...upcomingRace, status: 'finished' },
      loading: false,
      error: false,
    })
    mockUseRaceResults.mockReturnValue({ results: finishedResults, loading: false, error: false })

    const { container } = renderRace()
    revealResults()

    expect(screen.getByText('Winner Rider')).toBeInTheDocument()
    expect(screen.getByText('Zero Team')).toBeInTheDocument()
    expect(container.querySelector('svg[aria-label="Elevation profile"]')).not.toBeNull()
    expect(screen.getByText('Team points')).toBeInTheDocument()
    // Nowhere else to see it: no prize list on a finished race, so the
    // winner's own row is the only $20,000 on the screen.
    expect(screen.getAllByText('$20,000')).toHaveLength(1)
    expect(screen.queryByText('Prize list')).toBeNull()
    // A rider without a prize shows none; there is no prize list either.
    expect(screen.getByText('DNF Rider')).toBeInTheDocument()
    expect(screen.queryByText('$12,000')).toBeNull()
  })

  it('links each result row rider name to their profile', () => {
    mockUseRaceDetail.mockReturnValue({
      race: { ...upcomingRace, status: 'finished' },
      loading: false,
      error: false,
    })
    mockUseRaceResults.mockReturnValue({ results: finishedResults, loading: false, error: false })

    renderRace()
    revealResults()

    expect(screen.getByText('Winner Rider')).toHaveAttribute('href', '/riders/1')
    expect(screen.getByText('DNF Rider')).toHaveAttribute('href', '/riders/3')
  })

  it('shows each placed rider own prize, not a team lump sum', () => {
    mockUseRaceDetail.mockReturnValue({
      race: { ...upcomingRace, status: 'finished' },
      loading: false,
      error: false,
    })
    mockUseRaceResults.mockReturnValue({ results: finishedResults, loading: false, error: false })

    renderRace()
    revealResults()

    // Two riders from the same team (1st: $20,000, 2nd: $15,000) each carry
    // their own prize on their row; without the prize list those are the
    // only occurrences. The API-supplied team sum (35_000) is not shown
    // anywhere, and the team table is back to points only.
    expect(screen.getAllByText('$20,000')).toHaveLength(1)
    expect(screen.getAllByText('$15,000')).toHaveLength(1)
    expect(screen.queryByText('$35,000')).toBeNull()
    expect(screen.queryByText('Team points and prizes')).toBeNull()
  })

  it('renders without a squad panel when the manager has no team', () => {
    mockUseRaceDetail.mockReturnValue({ race: upcomingRace, loading: false, error: false })
    mockUseRaceResults.mockReturnValue({ results: null, loading: false, error: false })
    mockUseSquad.mockReturnValue({
      squad: null,
      loading: false,
      error: true,
      save: vi.fn(),
      saving: false,
      saveError: null,
    })

    renderRace()

    expect(screen.getByText('Circuit of Example')).toBeInTheDocument()
    expect(screen.queryByText('Select squad')).toBeNull()
  })

  it('renders a plain message for a failed race', () => {
    mockUseRaceDetail.mockReturnValue({
      race: { ...upcomingRace, status: 'failed' },
      loading: false,
      error: false,
    })
    mockUseRaceResults.mockReturnValue({ results: null, loading: false, error: false })

    renderRace()

    expect(screen.getByText('This race did not run.')).toBeInTheDocument()
  })

  it('lists its markers for an upcoming race', () => {
    mockUseRaceDetail.mockReturnValue({
      race: { ...upcomingRace, markers },
      loading: false,
      error: false,
    })
    mockUseRaceResults.mockReturnValue({ results: null, loading: false, error: false })
    mockUseSquad.mockReturnValue({
      squad,
      loading: false,
      error: false,
      save: vi.fn(),
      saving: false,
      saveError: null,
    })

    renderRace()

    expect(screen.getByText('Sprint · Line One · km 40.0')).toBeInTheDocument()
    expect(screen.getByText('Mountain · Summit · km 80.0')).toBeInTheDocument()
    expect(screen.queryByText('Sprints and summits')).toBeNull()
  })

  it('shows the first three over each marker for a finished race', () => {
    mockUseRaceDetail.mockReturnValue({
      race: { ...upcomingRace, status: 'finished', markers },
      loading: false,
      error: false,
    })
    mockUseRaceResults.mockReturnValue({ results: finishedResultsWithMarkers, loading: false, error: false })

    renderRace()
    revealResults()

    expect(screen.getByText('Sprints and summits')).toBeInTheDocument()
    expect(screen.getByText('Sprint · Line One')).toBeInTheDocument()
    expect(screen.getByText('km 40.0')).toBeInTheDocument()
    // Each crossing rider name appears once in the results table and again
    // in the marker card — a released rider's crossing still names them.
    expect(screen.getAllByText('Winner Rider')).toHaveLength(2)
    expect(screen.getAllByText('Second Rider')).toHaveLength(2)
    expect(screen.getAllByText('DNF Rider')).toHaveLength(2)
  })

  it('shows no marker card for a finished race without markers', () => {
    mockUseRaceDetail.mockReturnValue({
      race: { ...upcomingRace, status: 'finished', markers: [] },
      loading: false,
      error: false,
    })
    mockUseRaceResults.mockReturnValue({ results: finishedResults, loading: false, error: false })

    renderRace()
    revealResults()

    expect(screen.queryByText('Sprints and summits')).toBeNull()
  })

  it('hides a finished race results until Show results is clicked', () => {
    mockUseRaceDetail.mockReturnValue({
      race: { ...upcomingRace, status: 'finished' },
      loading: false,
      error: false,
    })
    mockUseRaceResults.mockReturnValue({ results: finishedResults, loading: false, error: false })

    renderRace()
    expect(screen.queryByText('Winner Rider')).toBeNull()
    // Nothing is asked for until the player asks to see it.
    expect(mockUseRaceResults).toHaveBeenLastCalledWith(42, false)

    revealResults()

    expect(screen.getByText('Winner Rider')).toBeInTheDocument()
    expect(mockUseRaceResults).toHaveBeenLastCalledWith(42, true)
  })

  it('hides the results again', () => {
    mockUseRaceDetail.mockReturnValue({
      race: { ...upcomingRace, status: 'finished' },
      loading: false,
      error: false,
    })
    mockUseRaceResults.mockReturnValue({ results: finishedResults, loading: false, error: false })

    renderRace()
    revealResults()
    fireEvent.click(screen.getByRole('button', { name: 'Hide results' }))

    expect(screen.queryByText('Winner Rider')).toBeNull()
    expect(mockUseRaceResults).toHaveBeenLastCalledWith(42, false)
  })

  it('shows Watch race when a replay exists', () => {
    mockUseRaceDetail.mockReturnValue({
      race: { ...upcomingRace, status: 'finished', has_replay: true },
      loading: false,
      error: false,
    })

    renderRace()

    expect(screen.getByRole('button', { name: 'Watch race' })).toBeInTheDocument()
    expect(screen.queryByText('No replay is available for this race.')).toBeNull()
  })

  it('shows the no-replay note when there is no replay', () => {
    mockUseRaceDetail.mockReturnValue({
      race: { ...upcomingRace, status: 'finished', has_replay: false },
      loading: false,
      error: false,
    })

    renderRace()

    expect(screen.getByText('No replay is available for this race.')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Watch race' })).toBeNull()
  })
})