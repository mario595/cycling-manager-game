import { fireEvent, render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import type { Me, Rider } from '../api'
import { useAuth } from '../useAuth'
import { useRoster } from '../useRoster'
import { Roster } from './Roster'

vi.mock('../useAuth', () => ({ useAuth: vi.fn() }))
vi.mock('../useRoster', () => ({ useRoster: vi.fn() }))

const mockUseAuth = vi.mocked(useAuth)
const mockUseRoster = vi.mocked(useRoster)

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
  mockUseRoster.mockReturnValue({
    riders,
    squadValue: 135000,
    salaryReview: null,
    loading: false,
    error: false,
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
    })

    renderRoster()

    expect(screen.queryByText('Season-end salary review')).not.toBeInTheDocument()
  })
})
