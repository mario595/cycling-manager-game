import { render, screen } from '@testing-library/react'
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
  ],
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

    expect(screen.getByRole('button', { name: 'Hire' })).toBeDisabled()
    expect(screen.getByText(/cannot afford/i)).toBeInTheDocument()
  })

  it('enables Hire when the balance covers the fee', () => {
    renderStaff()

    expect(screen.getByRole('button', { name: 'Hire' })).toBeEnabled()
    expect(screen.queryByText(/cannot afford/i)).not.toBeInTheDocument()
  })
})
