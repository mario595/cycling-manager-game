import { render, screen } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { describe, expect, it, vi } from 'vitest'

import type { RiderProfile as RiderProfileData } from '../api'
import { useRiderProfile } from '../useRiderProfile'
import { RiderProfile } from './RiderProfile'

vi.mock('../useRiderProfile', () => ({ useRiderProfile: vi.fn() }))

const mockUseRiderProfile = vi.mocked(useRiderProfile)

const profile: RiderProfileData = {
  id: 12,
  name: 'Profile Rider',
  speciality: 'Climber',
  nationality: 'Spain',
  age: 24,
  height_cm: 176,
  weight_kg: 61,
  climb: 8,
  sprint: 3,
  flat: 5,
  resistance: 6,
  positioning: 5,
  freshness: 7,
  weekly_salary: 4200,
  market_value: 310_000,
  release_cost: null,
  final_season: false,
  team: { id: 3, name: 'Profile Team', code: 'PFT' },
  current_week: { season: 1, week: 7 },
  retired: null,
  attribute_history: [
    { season: null, week: null, climb: 7, sprint: 3, flat: 5, resistance: 6, positioning: 5 },
  ],
  races: [
    {
      race: { id: 41, name: 'Opening Classic', starts_at: '2027-03-15T10:00:00Z' },
      team: { id: 3, name: 'Profile Team', code: 'PFT' },
      position: 2,
      finish_time: 3642,
      winner_time: 3600,
      finished: true,
    },
    {
      race: { id: 42, name: 'Windy Coastal', starts_at: '2027-03-20T13:00:00Z' },
      team: { id: 3, name: 'Profile Team', code: 'PFT' },
      position: 5,
      finish_time: null,
      winner_time: 3500,
      finished: false,
    },
  ],
  career: { starts: 2, wins: 0, podiums: 0, top_tens: 1, dnfs: 1 },
  development_squad: null,
}

function renderRiderProfile() {
  return render(
    <MemoryRouter initialEntries={['/riders/12']}>
      <Routes>
        <Route path="/riders/:riderId" element={<RiderProfile />} />
      </Routes>
    </MemoryRouter>,
  )
}

describe('RiderProfile', () => {
  it('renders the full profile with money, career numbers and a gap', () => {
    mockUseRiderProfile.mockReturnValue({ profile, loading: false, notFound: false, error: false })

    renderRiderProfile()

    expect(screen.getByText('Profile Rider')).toBeInTheDocument()
    expect(screen.getByText(/Profile Team/)).toBeInTheDocument()
    expect(screen.getByText('$4,200')).toBeInTheDocument()
    expect(screen.getByText('$310,000')).toBeInTheDocument()
    expect(screen.getByText('RACES').parentElement?.textContent).toContain('2')
    expect(screen.getByText('TOP 10').parentElement?.textContent).toContain('1')
    expect(screen.getByText('+0:42')).toBeInTheDocument()
    expect(screen.getAllByText('DNF').length).toBeGreaterThan(0)
    expect(screen.queryByRole('button')).toBeNull()
  })

  it('shows Free agent when the rider has no team', () => {
    mockUseRiderProfile.mockReturnValue({
      profile: { ...profile, team: null },
      loading: false,
      notFound: false,
      error: false,
    })

    renderRiderProfile()

    expect(screen.getByText(/Free agent/)).toBeInTheDocument()
  })

  it('shows retirement details in place of the team', () => {
    mockUseRiderProfile.mockReturnValue({
      profile: { ...profile, team: null, retired: { season: 1, week: 11 } },
      loading: false,
      notFound: false,
      error: false,
    })

    renderRiderProfile()

    expect(screen.getByText(/Retired · Season 1, Week 11/)).toBeInTheDocument()
  })

  it("shows a development squad rider's squad and no salary figure", () => {
    mockUseRiderProfile.mockReturnValue({
      profile: {
        ...profile,
        team: null,
        development_squad: { id: 9, name: 'Youth Team', code: 'YTH' },
      },
      loading: false,
      notFound: false,
      error: false,
    })

    renderRiderProfile()

    expect(screen.getByText(/Youth Team · Development squad/)).toBeInTheDocument()
    expect(screen.getByText('Paid by squad')).toBeInTheDocument()
    expect(screen.queryByText('$4,200')).not.toBeInTheDocument()
  })

  it('tags a rider whose season is their last in the page heading', () => {
    mockUseRiderProfile.mockReturnValue({
      profile: { ...profile, age: 34, final_season: true },
      loading: false,
      notFound: false,
      error: false,
    })

    renderRiderProfile()

    expect(screen.getByText('LAST SEASON')).toBeInTheDocument()
  })

  it('does not tag a rider who has seasons left', () => {
    mockUseRiderProfile.mockReturnValue({ profile, loading: false, notFound: false, error: false })

    renderRiderProfile()

    expect(screen.queryByText('LAST SEASON')).not.toBeInTheDocument()
  })

  it('shows a dash for a DNF row', () => {
    mockUseRiderProfile.mockReturnValue({ profile, loading: false, notFound: false, error: false })

    renderRiderProfile()

    const dnfRow = screen.getByText('Windy Coastal').closest('div')?.parentElement
    expect(dnfRow?.textContent).toContain('—')
  })

  it('shows an empty state with no races', () => {
    mockUseRiderProfile.mockReturnValue({
      profile: { ...profile, races: [] },
      loading: false,
      notFound: false,
      error: false,
    })

    renderRiderProfile()

    expect(screen.getByText('No races yet.')).toBeInTheDocument()
  })

  it('shows the "no longer part of the game" state on a 404', () => {
    mockUseRiderProfile.mockReturnValue({ profile: null, loading: false, notFound: true, error: false })

    renderRiderProfile()

    expect(screen.getByText('This rider is no longer part of the game.')).toBeInTheDocument()
  })

  it('shows a generic error state', () => {
    mockUseRiderProfile.mockReturnValue({ profile: null, loading: false, notFound: false, error: true })

    renderRiderProfile()

    expect(screen.getByText("Couldn't load this rider.")).toBeInTheDocument()
  })

  it('never shows a points figure', () => {
    mockUseRiderProfile.mockReturnValue({ profile, loading: false, notFound: false, error: false })

    renderRiderProfile()

    expect(screen.queryByText(/points/i)).toBeNull()
  })
})
