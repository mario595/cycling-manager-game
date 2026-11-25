import { fireEvent, render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import type { Me, Sponsors as SponsorsPayload } from '../api'
import { signOffer } from '../api'
import { useAuth } from '../useAuth'
import { useSponsors } from '../useSponsors'
import { Sponsors } from './Sponsors'

vi.mock('../useAuth', () => ({ useAuth: vi.fn() }))
vi.mock('../useSponsors', () => ({ useSponsors: vi.fn() }))
vi.mock('../api', async () => {
  const actual = await vi.importActual<typeof import('../api')>('../api')
  return { ...actual, signOffer: vi.fn() }
})

const mockUseAuth = vi.mocked(useAuth)
const mockUseSponsors = vi.mocked(useSponsors)
const mockSignOffer = vi.mocked(signOffer)

const manager: Me = {
  authenticated: true,
  display_name: 'Mario',
  team: { id: 1, name: 'Squad Team', code: 'SQD', sponsor_missing: false, guaranteed_weekly: null },
  lost_team: null,
}

const offers: SponsorsPayload['offers'] = [
  {
    id: 1, sponsor_name: 'Velocore', profile: 'steady', label: 'Steady',
    blurb: 'Pays the same every week, whatever happens.',
    weekly_base: 4_250, floor_amount: 4_250, ceiling_amount: 4_250,
  },
  {
    id: 2, sponsor_name: 'Ridgeline Bikes', profile: 'balanced', label: 'Performance-driven',
    blurb: "Pays more when you score, less when you don't.",
    weekly_base: 5_000, floor_amount: 3_000, ceiling_amount: 8_000,
  },
  {
    id: 3, sponsor_name: 'Pinnacle Sports', profile: 'demanding', label: 'Results-hungry',
    blurb: 'Pays big for big results — and little for none.',
    weekly_base: 6_250, floor_amount: 2_188, ceiling_amount: 13_750,
  },
]

function renderSponsors() {
  return render(
    <MemoryRouter>
      <Sponsors />
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
    refresh: vi.fn(),
  })
  mockUseSponsors.mockReturnValue({
    sponsors: { contract: null, offers }, loading: false, error: false, refresh: vi.fn(),
  })
})

describe('Sponsors', () => {
  it('renders nothing while loading', () => {
    mockUseSponsors.mockReturnValue({ sponsors: null, loading: true, error: false, refresh: vi.fn() })

    const { container } = renderSponsors()

    expect(container).toBeEmptyDOMElement()
  })

  it('renders three offers with their ranges', () => {
    renderSponsors()

    expect(screen.getByText('Velocore')).toBeInTheDocument()
    expect(screen.getByText('Ridgeline Bikes')).toBeInTheDocument()
    expect(screen.getByText('Pinnacle Sports')).toBeInTheDocument()
    expect(screen.getByText('$3,000 – $8,000')).toBeInTheDocument()
    expect(screen.getAllByText('Sign')).toHaveLength(3)
  })

  it('formats money with $', () => {
    renderSponsors()

    expect(screen.getByText('$4,250 – $4,250')).toBeInTheDocument()
    expect(screen.getByText('$2,188 – $13,750')).toBeInTheDocument()
  })

  it('signing calls the API and refreshes', async () => {
    const refresh = vi.fn()
    mockUseSponsors.mockReturnValue({
      sponsors: { contract: null, offers }, loading: false, error: false, refresh,
    })
    mockSignOffer.mockResolvedValue(undefined)

    renderSponsors()
    fireEvent.click(screen.getAllByText('Sign')[0])

    await screen.findByText('Velocore')  // wait for the click's microtask to settle
    expect(mockSignOffer).toHaveBeenCalledWith(1)
    expect(refresh).toHaveBeenCalled()
    // `me` too, so the dashboard banner and the sidebar dot go at once (#161).
    expect(mockUseAuth.mock.results[0].value.refresh).toHaveBeenCalled()
  })

  it('shows the signed contract instead of the pool', () => {
    mockUseSponsors.mockReturnValue({
      sponsors: {
        contract: {
          sponsor_name: 'Ridgeline Bikes', profile: 'balanced', label: 'Performance-driven',
          blurb: "Pays more when you score, less when you don't.",
          weekly_base: 5_000, floor_amount: 3_000, ceiling_amount: 8_000,
          signed_at: '2027-03-01T00:00:00Z',
        },
        offers: [],
      },
      loading: false, error: false, refresh: vi.fn(),
    })

    renderSponsors()

    expect(screen.getByText('Ridgeline Bikes')).toBeInTheDocument()
    expect(screen.queryByText('Sign')).not.toBeInTheDocument()
    expect(screen.getByText('$3,000 – $8,000')).toBeInTheDocument()
  })

  it('shows an error message when signing fails', async () => {
    mockSignOffer.mockRejectedValue(new Error('Your team already has a sponsor this season.'))

    renderSponsors()
    fireEvent.click(screen.getAllByText('Sign')[0])

    expect(await screen.findByText('Your team already has a sponsor this season.')).toBeInTheDocument()
  })
})
