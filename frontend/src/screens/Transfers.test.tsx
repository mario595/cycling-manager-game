import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { signFreeAgent, type FreeAgentPool, type Me } from '../api'
import { useAuth } from '../useAuth'
import { useFreeAgents } from '../useFreeAgents'
import { Transfers } from './Transfers'

vi.mock('../useAuth', () => ({ useAuth: vi.fn() }))
vi.mock('../useFreeAgents', () => ({ useFreeAgents: vi.fn() }))
vi.mock('../api', () => ({ signFreeAgent: vi.fn() }))

const mockUseAuth = vi.mocked(useAuth)
const mockUseFreeAgents = vi.mocked(useFreeAgents)
const mockSignFreeAgent = vi.mocked(signFreeAgent)

const manager: Me = {
  authenticated: true,
  display_name: 'Mario',
  team: { id: 1, name: 'Squad Team', code: 'SQD' },
  lost_team: null,
}

const pool: FreeAgentPool = {
  balance: 500_000,
  riders: [
    {
      id: 7,
      name: 'Coach One',
      speciality: 'climber',
      nationality: 'FR',
      age: 27,
      height_cm: 178,
      weight_kg: 70,
      climb: 9,
      sprint: 4,
      flat: 5,
      resistance: 5,
      positioning: 4,
      freshness: 10,
      weekly_salary: 3_900,
      market_value: 90_000,
      release_cost: null,
      signing_fee: 46_800,
    },
    {
      id: 8,
      name: 'Helper Two',
      speciality: 'rouleur',
      nationality: 'BE',
      age: 24,
      height_cm: 182,
      weight_kg: 74,
      climb: 2,
      sprint: 5,
      flat: 8,
      resistance: 6,
      positioning: 5,
      freshness: 10,
      weekly_salary: 1_700,
      market_value: 40_000,
      release_cost: null,
      signing_fee: 20_000,
    },
    {
      id: 9,
      name: 'Sprinter Three',
      speciality: 'sprinter',
      nationality: 'IT',
      age: 25,
      height_cm: 180,
      weight_kg: 76,
      climb: 1,
      sprint: 9,
      flat: 5,
      resistance: 4,
      positioning: 6,
      freshness: 10,
      weekly_salary: 2_800,
      market_value: 75_000,
      release_cost: null,
      signing_fee: 34_000,
    },
  ],
}

function visibleNames() {
  return screen.getAllByText(/^(Coach One|Helper Two|Sprinter Three)$/).map((el) => el.textContent)
}

function renderTransfers() {
  return render(
    <MemoryRouter>
      <Transfers />
    </MemoryRouter>,
  )
}

beforeEach(() => {
  vi.clearAllMocks()
  mockUseAuth.mockReturnValue({
    me: manager,
    loading: false,
    register: vi.fn(),
    login: vi.fn(),
    logout: vi.fn(),
    claim: vi.fn(),
    acknowledgeLostTeam: vi.fn(),
  })
  mockUseFreeAgents.mockReturnValue({ pool, loading: false, error: false, refresh: vi.fn() })
  mockSignFreeAgent.mockResolvedValue(undefined)
})

describe('Transfers', () => {
  it('renders the signing fee and weekly salary on the card', () => {
    renderTransfers()

    expect(screen.getByText('Fee $46,800')).toBeInTheDocument()
    expect(screen.getByText('$3,900/wk')).toBeInTheDocument()
  })

  it('disables Sign with a reason when the fee exceeds the balance', () => {
    mockUseFreeAgents.mockReturnValue({
      pool: { ...pool, balance: 10_000 },
      loading: false,
      error: false,
      refresh: vi.fn(),
    })

    renderTransfers()

    for (const button of screen.getAllByRole('button', { name: 'Sign' })) {
      expect(button).toBeDisabled()
    }
    expect(screen.getAllByText(/cannot afford/i)).toHaveLength(3)
  })

  it('enables Sign when the balance covers the fee', () => {
    renderTransfers()

    for (const button of screen.getAllByRole('button', { name: 'Sign' })) {
      expect(button).toBeEnabled()
    }
    expect(screen.queryByText(/cannot afford/i)).not.toBeInTheDocument()
  })

  it('lists the cheapest signing fee first by default', () => {
    renderTransfers()

    expect(visibleNames()).toEqual(['Helper Two', 'Sprinter Three', 'Coach One'])
  })

  it('sorts by name', () => {
    renderTransfers()

    fireEvent.click(screen.getByRole('button', { name: 'Name' }))

    expect(visibleNames()).toEqual(['Coach One', 'Helper Two', 'Sprinter Three'])
  })

  it('filters the pool by speciality', () => {
    renderTransfers()

    fireEvent.click(screen.getByRole('button', { name: 'sprinter' }))

    expect(visibleNames()).toEqual(['Sprinter Three'])
    expect(screen.getByText(/1 of 3 free agents/)).toBeInTheDocument()
  })

  it('returns every rider when the All filter is back on', () => {
    renderTransfers()

    fireEvent.click(screen.getByRole('button', { name: 'sprinter' }))
    fireEvent.click(screen.getByRole('button', { name: 'All' }))

    expect(visibleNames()).toEqual(['Helper Two', 'Sprinter Three', 'Coach One'])
    expect(screen.getByText(/3 of 3 free agents/)).toBeInTheDocument()
  })

  it('signs a rider and re-fetches the pool', async () => {
    const refresh = vi.fn()
    mockUseFreeAgents.mockReturnValue({ pool, loading: false, error: false, refresh })
    const sign = mockSignFreeAgent.mockResolvedValue(undefined)

    renderTransfers()

    fireEvent.click(screen.getAllByRole('button', { name: 'Sign' })[0])

    await waitFor(() => expect(sign).toHaveBeenCalledWith(8))
    await waitFor(() => expect(refresh).toHaveBeenCalled())
  })
})