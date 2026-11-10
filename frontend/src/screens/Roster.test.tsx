import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import type { Me, Rider, Solvency } from '../api'
import { forceSell, listForAuction, releaseRider } from '../api'
import { useAuth } from '../useAuth'
import { useRoster } from '../useRoster'
import { useSolvency } from '../useSolvency'
import { Roster } from './Roster'

vi.mock('../useAuth', () => ({ useAuth: vi.fn() }))
vi.mock('../useRoster', () => ({ useRoster: vi.fn() }))
vi.mock('../useSolvency', () => ({ useSolvency: vi.fn() }))
vi.mock('../api', () => ({ releaseRider: vi.fn(), listForAuction: vi.fn(), forceSell: vi.fn() }))

const mockUseAuth = vi.mocked(useAuth)
const mockUseRoster = vi.mocked(useRoster)
const mockReleaseRider = vi.mocked(releaseRider)
const mockListForAuction = vi.mocked(listForAuction)
const mockForceSell = vi.mocked(forceSell)
const mockUseSolvency = vi.mocked(useSolvency)

const solvent: Solvency = {
  insolvent: false,
  balance: 100_000,
  shortfall: 0,
  target: 0,
  cut_so_far: 0,
  outgoings: 0,
  income: 0,
  strikes: 0,
  paydays_left: null,
  deadline: null,
  roster_size: 12,
  roster_floor: 4,
}
const insolvent: Solvency = { ...solvent, insolvent: true, shortfall: 5_000, target: 5_000, paydays_left: 3 }

function showSolvency(solvency: Solvency) {
  mockUseSolvency.mockReturnValue({ solvency, loading: false, error: false, refresh: vi.fn() })
}

const manager: Me = {
  authenticated: true,
  display_name: 'Mario',
  team: { id: 1, name: 'Squad Team', code: 'SQD' },
  lost_team: null,
}

const riders: Rider[] = [
  {
    id: 1,
    name: 'Alba Sanchez',
    speciality: 'climber',
    nationality: 'Spain',
    age: 24,
    height_cm: 170,
    weight_kg: 60,
    climb: 8,
    sprint: 4,
    flat: 5,
    resistance: 6,
    positioning: 6,
    freshness: 10,
    weekly_salary: 3200,
    market_value: 40000,
    release_cost: 12000,
    final_season: false,
  },
  {
    id: 2,
    name: 'Bruno Ruiz',
    speciality: 'sprinter',
    nationality: 'Spain',
    age: 22,
    height_cm: 184,
    weight_kg: 78,
    climb: 3,
    sprint: 8,
    flat: 7,
    resistance: 4,
    positioning: 6,
    freshness: 10,
    weekly_salary: 900,
    market_value: 95000,
    release_cost: 3000,
    final_season: false,
  },
]

function rosterWith(refresh = vi.fn()) {
  mockUseRoster.mockReturnValue({
    riders,
    squadValue: 135_000,
    salaryReview: null,
    loading: false,
    error: false,
    refresh,
  })
}

function renderRoster() {
  return render(
    <MemoryRouter>
      <Roster />
    </MemoryRouter>,
  )
}

beforeEach(() => {
  showSolvency(solvent)
  mockUseAuth.mockReturnValue({
    me: manager,
    loading: false,
    register: vi.fn(),
    login: vi.fn(),
    logout: vi.fn(),
    claim: vi.fn(),
    acknowledgeLostTeam: vi.fn(),
  })
  mockUseRoster.mockReturnValue({
    riders,
    squadValue: 135000,
    salaryReview: null,
    loading: false,
    error: false,
    refresh: vi.fn(),
  })
})

describe('Roster', () => {
  it('renders nothing while loading', () => {
    mockUseRoster.mockReturnValue({
      riders: null,
      squadValue: null,
      salaryReview: null,
      loading: true,
      error: false,
      refresh: vi.fn(),
    })

    const { container } = renderRoster()

    expect(container).toBeEmptyDOMElement()
  })

  it("renders each rider's weekly salary formatted as money", () => {
    renderRoster()

    expect(screen.getByText('$3,200/wk')).toBeInTheDocument()
    expect(screen.getByText('$900/wk')).toBeInTheDocument()
  })

  it('sorts by salary when the Salary chip is picked', () => {
    renderRoster()

    fireEvent.click(screen.getByText('Salary'))

    const cards = screen.getAllByText(/\/wk$/)
    // Descending, so the higher salary card renders first.
    expect(cards[0]).toHaveTextContent('$3,200/wk')
    expect(cards[1]).toHaveTextContent('$900/wk')
  })

  it("renders each rider's market value formatted as money", () => {
    renderRoster()

    expect(screen.getByText('$40,000')).toBeInTheDocument()
    expect(screen.getByText('$95,000')).toBeInTheDocument()
  })

  it('renders the squad value total in the header', () => {
    renderRoster()

    expect(screen.getByText('$135,000')).toBeInTheDocument()
  })

  it('tags a rider in their final season on the card and in the panel', () => {
    const veteran: Rider = { ...riders[0], id: 3, name: 'Vera Old', final_season: true }
    mockUseRoster.mockReturnValue({
      riders: [veteran, ...riders],
      squadValue: 135_000,
      salaryReview: null,
      loading: false,
      error: false,
      refresh: vi.fn(),
    })

    renderRoster()

    // One on the card, one beside the name in the panel once it is opened.
    expect(screen.getAllByText('LAST SEASON')).toHaveLength(1)
    fireEvent.click(screen.getByText('Vera Old'))
    expect(screen.getAllByText('LAST SEASON')).toHaveLength(2)
  })

  it('does not tag a rider who is not in their final season', () => {
    renderRoster()

    expect(screen.queryByText('LAST SEASON')).not.toBeInTheDocument()
  })

  it('sorts by value when the Value chip is picked, differently from Salary', () => {
    renderRoster()

    fireEvent.click(screen.getByText('Value'))

    // Scoped to the rider cards (buttons), so the header's squad-value
    // stat tile — which matches the same money pattern — is excluded.
    const cardNames = screen.getAllByRole('button').map((button) => button.textContent)
    const withValue = cardNames.filter((name) => /\$[\d,]+$/.test(name ?? ''))
    // Descending by market_value, so Bruno ($95,000) renders before Alba
    // ($40,000) — the opposite order from sorting by salary.
    expect(withValue[0]).toContain('$95,000')
    expect(withValue[1]).toContain('$40,000')
  })

  it('shows the release cost when a rider is picked', () => {
    renderRoster()

    fireEvent.click(screen.getByText('Alba Sanchez'))

    expect(screen.getByText('Release $12,000')).toBeInTheDocument()
  })

  it('links the open panel to the rider\'s full profile', () => {
    renderRoster()

    fireEvent.click(screen.getByText('Alba Sanchez'))

    expect(screen.getByText('Full profile →')).toHaveAttribute('href', '/riders/1')
  })

  it('notes when releasing a rider is free', () => {
    const freeRider: Rider = { ...riders[0], id: 3, name: 'Carla Díaz', release_cost: 0 }
    mockUseRoster.mockReturnValue({
      riders: [freeRider, ...riders],
      squadValue: 135_000,
      salaryReview: null,
      loading: false,
      error: false,
      refresh: vi.fn(),
    })

    renderRoster()

    fireEvent.click(screen.getByText('Carla Díaz'))

    expect(screen.getByText(/claim cooldown/)).toBeInTheDocument()
  })

  it('releases a rider and refetches the roster', async () => {
    const refresh = vi.fn()
    const release = mockReleaseRider.mockResolvedValue(undefined)
    mockUseRoster.mockReturnValue({
      riders,
      squadValue: 135_000,
      salaryReview: null,
      loading: false,
      error: false,
      refresh,
    })

    renderRoster()

    fireEvent.click(screen.getByText('Alba Sanchez'))
    fireEvent.click(screen.getByRole('button', { name: 'Release' }))

    await waitFor(() => expect(release).toHaveBeenCalledWith(1))
    await waitFor(() => expect(refresh).toHaveBeenCalled())
  })

  it('lists a rider for auction and refetches the roster', async () => {
    const refresh = vi.fn()
    const list = mockListForAuction.mockResolvedValue(undefined)
    mockUseRoster.mockReturnValue({
      riders,
      squadValue: 135_000,
      salaryReview: null,
      loading: false,
      error: false,
      refresh,
    })

    renderRoster()

    fireEvent.click(screen.getByText('Alba Sanchez'))
    fireEvent.click(screen.getByRole('button', { name: 'List for auction' }))

    await waitFor(() => expect(list).toHaveBeenCalledWith(1))
    await waitFor(() => expect(refresh).toHaveBeenCalled())
  })

  it('offers no force sale to a solvent team', () => {
    renderRoster()

    fireEvent.click(screen.getByText('Alba Sanchez'))

    expect(screen.queryByRole('button', { name: 'Force sale' })).not.toBeInTheDocument()
  })

  it('asks for confirmation, then force-sells and refetches both screens', async () => {
    const refresh = vi.fn()
    const refreshSolvency = vi.fn()
    rosterWith(refresh)
    mockUseSolvency.mockReturnValue({
      solvency: insolvent, loading: false, error: false, refresh: refreshSolvency,
    })
    const sell = mockForceSell.mockResolvedValue(undefined)

    renderRoster()

    fireEvent.click(screen.getByText('Alba Sanchez'))
    fireEvent.click(screen.getByRole('button', { name: 'Force sale' }))
    expect(sell).not.toHaveBeenCalled()
    expect(screen.getByText(/does not come back/)).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Confirm force sale' }))

    await waitFor(() => expect(sell).toHaveBeenCalledWith(1))
    await waitFor(() => expect(refresh).toHaveBeenCalled())
    await waitFor(() => expect(refreshSolvency).toHaveBeenCalled())
  })

  it('disables the force sale at the roster floor', () => {
    rosterWith()
    showSolvency({ ...insolvent, roster_size: 4, roster_floor: 4 })

    renderRoster()

    fireEvent.click(screen.getByText('Alba Sanchez'))

    expect(screen.getByRole('button', { name: 'Force sale' })).toBeDisabled()
    expect(screen.getByText('A team needs at least 4 riders to race.')).toBeInTheDocument()
  })

  it('shows the refusal when the server rejects the force sale', async () => {
    rosterWith()
    showSolvency(insolvent)
    mockForceSell.mockRejectedValue(new Error('A team needs at least 4 riders to race.'))

    renderRoster()

    fireEvent.click(screen.getByText('Alba Sanchez'))
    fireEvent.click(screen.getByRole('button', { name: 'Force sale' }))
    fireEvent.click(screen.getByRole('button', { name: 'Confirm force sale' }))

    expect(await screen.findByText('A team needs at least 4 riders to race.')).toBeInTheDocument()
  })

  it('renders the salary review panel with the wage bill and one row per change', () => {
    mockUseRoster.mockReturnValue({
      riders,
      squadValue: 135000,
      salaryReview: {
        season_number: 9,
        payroll_before: 2300,
        payroll_after: 2400,
        // Bruno first in the payload: the panel must sort by absolute
        // delta descending, so Alba's bigger raise leads.
        changes: [
          { rider_id: 2, rider_name: 'Bruno Ruiz', from_value: 900, to_value: 500 },
          { rider_id: 1, rider_name: 'Alba Sanchez', from_value: 3200, to_value: 3800 },
        ],
      },
      loading: false,
      error: false,
      refresh: vi.fn(),
    })

    renderRoster()

    expect(screen.getByText('Season-end salary review')).toBeInTheDocument()
    expect(screen.getByText('SEASON 9')).toBeInTheDocument()
    // The wage bill row: before → after, both $-prefixed.
    expect(screen.getByText('Weekly wage bill')).toBeInTheDocument()
    expect(screen.getByText('$2,300')).toBeInTheDocument()
    expect(screen.getByText('$2,400')).toBeInTheDocument()
    // A row per change, biggest movement first, each with its delta. The
    // rider names also appear on the roster cards below, so the panel rows
    // are proven by the deltas' order rather than by name presence.
    expect(screen.getAllByText('Alba Sanchez')).toHaveLength(2)  // card + review row
    expect(screen.getAllByText('Bruno Ruiz')).toHaveLength(2)
    const deltas = screen.getAllByText(/^[+−]/).map((element) => element.textContent)
    expect(deltas).toEqual(['+$100', '+$600', '−$400'])
  })

  it('renders nothing when salary_review is null', () => {
    renderRoster()

    expect(screen.queryByText('Season-end salary review')).not.toBeInTheDocument()
  })

  it('renders nothing when the review has no changes', () => {
    mockUseRoster.mockReturnValue({
      riders,
      squadValue: 135000,
      salaryReview: {
        season_number: 5,
        payroll_before: 4000,
        payroll_after: 4000,
        changes: [],
      },
      loading: false,
      error: false,
      refresh: vi.fn(),
    })

    renderRoster()

    expect(screen.queryByText('Season-end salary review')).not.toBeInTheDocument()
  })
})