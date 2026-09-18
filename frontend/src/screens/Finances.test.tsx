import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import type { Finances as FinancesPayload, Me } from '../api'
import { color } from '../theme'
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
  fanbase: 10_650,
  fanbase_change: 650,
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

  it('renders the fanbase tile with its weekly change', () => {
    mockUseFinances.mockReturnValue({
      finances: { ...finances, fanbase: 10_650, fanbase_change: 650 },
      loading: false,
      error: false,
      refresh: vi.fn(),
    })

    renderFinances()

    expect(screen.getByText('10,650')).toBeInTheDocument()
    expect(screen.getByText('+650 this week')).toBeInTheDocument()
  })

  it('renders a negative weekly change in the negative colour', () => {
    mockUseFinances.mockReturnValue({
      finances: { ...finances, fanbase: 9_850, fanbase_change: -150 },
      loading: false,
      error: false,
      refresh: vi.fn(),
    })

    renderFinances()

    const change = screen.getByText('−150 this week')
    expect(change).toBeInTheDocument()
    expect(change).toHaveStyle({ color: color.negative })
  })

  it('renders a merchandise entry with its label and a positive amount', () => {
    mockUseFinances.mockReturnValue({
      finances: {
        ...finances,
        entries: [
          {
            id: 3,
            kind: 'merchandise',
            description: 'Merchandise revenue',
            amount: 420,
            occurred_at: '2027-03-08T00:00:00Z',
            rider_count: null,
            balance_after: 500_420,
          },
          ...finances.entries,
        ],
      },
      loading: false,
      error: false,
      refresh: vi.fn(),
    })

    renderFinances()

    expect(screen.getByText('Merchandise revenue')).toBeInTheDocument()
    expect(screen.getByText('+420')).toBeInTheDocument()
  })
})