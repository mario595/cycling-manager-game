import { fireEvent, render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import type { Me, Staff as StaffPayload } from '../api'
import { useAuth } from '../useAuth'
import { useStaff } from '../useStaff'
import { Staff } from './Staff'

vi.mock('../useAuth', () => ({ useAuth: vi.fn() }))
vi.mock('../useStaff', () => ({ useStaff: vi.fn() }))

const mockUseAuth = vi.mocked(useAuth)
const mockUseStaff = vi.mocked(useStaff)

const manager: Me = {
  authenticated: true,
  display_name: 'Mario',
  team: { id: 1, name: 'Squad Team', code: 'SQD' },
  lost_team: null,
}

const staff: StaffPayload = {
  trainer: null,
  balance: 500_000,
  pool: [
    {
      id: 7,
      name: 'Coach One',
      nationality: 'FR',
      speciality: 'climb',
      skills: { climb: 9, sprint: 4, flat: 5, resistance: 5, positioning: 4 },
      hire_fee: 46_800,
      weekly_salary: 3_900,
    },
    {
      id: 8,
      name: 'Helper Two',
      nationality: 'BE',
      speciality: 'flat',
      skills: { climb: 2, sprint: 5, flat: 8, resistance: 6, positioning: 5 },
      hire_fee: 20_000,
      weekly_salary: 1_700,
    },
    {
      id: 9,
      name: 'Sprinter Three',
      nationality: 'IT',
      speciality: 'sprint',
      skills: { climb: 1, sprint: 9, flat: 5, resistance: 4, positioning: 6 },
      hire_fee: 34_000,
      weekly_salary: 2_800,
    },
  ],
}

function visibleNames() {
  return screen.getAllByText(/^(Coach One|Helper Two|Sprinter Three)$/).map((el) => el.textContent)
}

function renderStaff() {
  return render(
    <MemoryRouter>
      <Staff />
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
  mockUseStaff.mockReturnValue({ staff, loading: false, error: false, refresh: vi.fn() })
})

describe('Staff', () => {
  it('renders the hire fee and weekly salary on the card', () => {
    renderStaff()

    expect(screen.getByText('Fee $46,800')).toBeInTheDocument()
    expect(screen.getByText('$3,900/week')).toBeInTheDocument()
  })

  it('disables Hire with a reason when the fee exceeds the balance', () => {
    mockUseStaff.mockReturnValue({
      staff: { ...staff, balance: 10_000 },
      loading: false,
      error: false,
      refresh: vi.fn(),
    })

    renderStaff()

    for (const button of screen.getAllByRole('button', { name: 'Hire' })) {
      expect(button).toBeDisabled()
    }
    expect(screen.getAllByText(/cannot afford/i)).toHaveLength(3)
  })

  it('enables Hire when the balance covers the fee', () => {
    renderStaff()

    for (const button of screen.getAllByRole('button', { name: 'Hire' })) {
      expect(button).toBeEnabled()
    }
    expect(screen.queryByText(/cannot afford/i)).not.toBeInTheDocument()
  })

  it('lists the cheapest fee first by default', () => {
    renderStaff()

    expect(visibleNames()).toEqual(['Helper Two', 'Sprinter Three', 'Coach One'])
  })

  it('sorts by salary', () => {
    renderStaff()

    fireEvent.click(screen.getByRole('button', { name: 'Salary' }))

    expect(visibleNames()).toEqual(['Helper Two', 'Sprinter Three', 'Coach One'])
  })

  it('sorts by name', () => {
    renderStaff()

    fireEvent.click(screen.getByRole('button', { name: 'Name' }))

    expect(visibleNames()).toEqual(['Coach One', 'Helper Two', 'Sprinter Three'])
  })

  it('filters the pool by speciality', () => {
    renderStaff()

    fireEvent.click(screen.getByRole('button', { name: 'climb' }))

    expect(visibleNames()).toEqual(['Coach One'])
    expect(screen.getByText(/1 of 3 trainers/)).toBeInTheDocument()
  })

  it('returns every trainer when the All filter is back on', () => {
    renderStaff()

    fireEvent.click(screen.getByRole('button', { name: 'climb' }))
    fireEvent.click(screen.getByRole('button', { name: 'All' }))

    expect(visibleNames()).toEqual(['Helper Two', 'Sprinter Three', 'Coach One'])
    expect(screen.getByText(/3 of 3 trainers/)).toBeInTheDocument()
  })
})
