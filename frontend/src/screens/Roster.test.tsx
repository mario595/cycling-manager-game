import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import type { Me, Rider } from '../api'
import { releaseRider } from '../api'
import { useAuth } from '../useAuth'
import { useRoster } from '../useRoster'
import { Roster } from './Roster'

vi.mock('../useAuth', () => ({ useAuth: vi.fn() }))
vi.mock('../useRoster', () => ({ useRoster: vi.fn() }))
vi.mock('../api', () => ({ releaseRider: vi.fn() }))

const mockUseAuth = vi.mocked(useAuth)
const mockUseRoster = vi.mocked(useRoster)
const mockReleaseRider = vi.mocked(releaseRider)

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
  },
]

function renderRoster() {
  return render(
    <MemoryRouter>
      <Roster />
    </MemoryRouter>,
  )
}

beforeEach(() => {
  mockUseAuth.mockReturnValue({
    me: manager,
    loading: false,
    register: vi.fn(),
    login: vi.fn(),
    logout: vi.fn(),
    claim: vi.fn(),
    acknowledgeLostTeam: vi.fn(),
  })
  mockUseRoster.mockReturnValue({ riders, squadValue: 135000, loading: false, error: false, refresh: vi.fn() })
})

describe('Roster', () => {
  it('renders nothing while loading', () => {
    mockUseRoster.mockReturnValue({ riders: null, squadValue: null, loading: true, error: false, refresh: vi.fn() })

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

  it('notes when releasing a rider is free', () => {
    const freeRider: Rider = { ...riders[0], id: 3, name: 'Carla Díaz', release_cost: 0 }
    mockUseRoster.mockReturnValue({
      riders: [freeRider, ...riders],
      squadValue: 135_000,
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
    mockUseRoster.mockReturnValue({ riders, squadValue: 135_000, loading: false, error: false, refresh })

    renderRoster()

    fireEvent.click(screen.getByText('Alba Sanchez'))
    fireEvent.click(screen.getByRole('button', { name: 'Release' }))

    await waitFor(() => expect(release).toHaveBeenCalledWith(1))
    await waitFor(() => expect(refresh).toHaveBeenCalled())
  })
})
