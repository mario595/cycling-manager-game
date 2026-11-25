import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { describe, expect, it, vi } from 'vitest'

import type { Me } from '../api'
import { useAuth } from '../useAuth'
import { SponsorBanner } from './SponsorBanner'

vi.mock('../useAuth', () => ({ useAuth: vi.fn() }))

const mockUseAuth = vi.mocked(useAuth)

const signed: Me = {
  authenticated: true,
  display_name: 'Mario',
  team: { id: 1, name: 'Squad Team', code: 'SQD', sponsor_missing: false, smallest_offer_weekly: null },
  lost_team: null,
}

function show(me: Me | null) {
  mockUseAuth.mockReturnValue({
    me,
    loading: false,
    register: vi.fn(),
    login: vi.fn(),
    logout: vi.fn(),
    claim: vi.fn(),
    acknowledgeLostTeam: vi.fn(),
    refresh: vi.fn(),
  })
  return render(
    <MemoryRouter>
      <SponsorBanner />
    </MemoryRouter>,
  )
}

function unsigned(smallest: number | null): Me {
  return { ...signed, team: { ...signed.team!, sponsor_missing: true, smallest_offer_weekly: smallest } }
}

describe('SponsorBanner', () => {
  it('renders nothing once the team has a sponsor', () => {
    const { container } = show(signed)

    expect(container).toBeEmptyDOMElement()
  })

  it('renders nothing for a manager with no team', () => {
    const { container } = show({ ...signed, team: null })

    expect(container).toBeEmptyDOMElement()
  })

  it('warns, names the smallest offer and links to Sponsors', () => {
    show(unsigned(9_640))

    expect(screen.getByText(/No sponsor this season/)).toBeInTheDocument()
    expect(screen.getByText(/Offers start at \$9,640 a week/)).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Pick an offer' })).toHaveAttribute('href', '/sponsors')
  })

  it('still warns when no offer amount is known', () => {
    show(unsigned(null))

    expect(screen.getByText(/No sponsor this season/)).toBeInTheDocument()
    expect(screen.queryByText(/Offers start at/)).toBeNull()
  })
})
