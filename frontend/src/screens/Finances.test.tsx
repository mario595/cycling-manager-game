import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import type { Finances as FinancesPayload, Me } from '../api'
import { useAuth } from '../useAuth'
import { useFinances } from '../useFinances'
import { Finances } from './Finances'

vi.mock('../useAuth', () => ({ useAuth: vi.fn() }))
vi.mock('../useFinances', () => ({ useFinances: vi.fn() }))

const mockUseAuth = vi.mocked(useAuth)
const mockUseFinances = vi.mocked(useFinances)

const manager: Me = {
  authenticated: true,
  display_name: 'Mario',
  team: { id: 1, name: 'Squad Team', code: 'SQD' },
}

const finances: FinancesPayload = {
  balance: 485_600,
  entries: [
    {
      id: 2,
      kind: 'wages',
      description: 'Weekly wages',
      amount: -14_400,
      occurred_at: '2027-03-08T00:00:00Z',
      rider_count: 12,
      balance_after: 485_600,
    },
    {
      id: 1,
      kind: 'starting_balance',
      description: 'Starting balance',
      amount: 500_000,
      occurred_at: '2027-03-01T00:00:00Z',
      rider_count: null,
      balance_after: 500_000,
    },
  ],
}

function renderFinances() {
  return render(
    <MemoryRouter>
      <Finances />
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
  })
  mockUseFinances.mockReturnValue({ finances, loading: false, error: false, refresh: vi.fn() })
})

describe('Finances', () => {
  it('renders nothing while loading', () => {
    mockUseFinances.mockReturnValue({ finances: null, loading: true, error: false, refresh: vi.fn() })

    const { container } = renderFinances()

    expect(container).toBeEmptyDOMElement()
  })

  it('renders the balance and the entries, newest first', () => {
    renderFinances()

    expect(screen.getByText('485,600')).toBeInTheDocument()
    // Newest entry is first in the payload and rendered first.
    expect(screen.getByText('Weekly wages')).toBeInTheDocument()
    expect(screen.getByText(/WEEKLY WAGES/)).toBeInTheDocument()
    expect(screen.getByText('after: 485,600')).toBeInTheDocument()
    expect(screen.getByText('after: 500,000')).toBeInTheDocument()
  })

  it('shows the warning when the balance is negative', () => {
    mockUseFinances.mockReturnValue({
      finances: { ...finances, balance: -12_400 },
      loading: false,
      error: false,
      refresh: vi.fn(),
    })

    renderFinances()

    expect(screen.getByText(/Your balance is negative/)).toBeInTheDocument()
  })
})