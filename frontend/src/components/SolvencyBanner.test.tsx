import { render, screen } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import type { Solvency } from '../api'
import { useSolvency } from '../useSolvency'
import { SolvencyBanner } from './SolvencyBanner'

vi.mock('../useSolvency', () => ({ useSolvency: vi.fn() }))

const mockUseSolvency = vi.mocked(useSolvency)

const insolvent: Solvency = {
  insolvent: true,
  balance: -12_000,
  shortfall: 8_000,
  target: 10_000,
  cut_so_far: 2_000,
  outgoings: 30_000,
  income: 22_000,
  strikes: 1,
  paydays_left: 3,
  deadline: '2027-03-22T00:00:00Z',
  roster_size: 8,
  roster_floor: 4,
}

function show(solvency: Solvency | null) {
  mockUseSolvency.mockReturnValue({ solvency, loading: false, error: false, refresh: vi.fn() })
}

beforeEach(() => {
  show(insolvent)
})

describe('SolvencyBanner', () => {
  it('renders nothing for a solvent team', () => {
    show({ ...insolvent, insolvent: false })

    const { container } = render(<SolvencyBanner />)

    expect(container).toBeEmptyDOMElement()
  })

  it('renders nothing while the standing has not loaded', () => {
    show(null)

    const { container } = render(<SolvencyBanner />)

    expect(container).toBeEmptyDOMElement()
  })

  it('states the shortfall, the deadline and the progress', () => {
    render(<SolvencyBanner />)

    const alert = screen.getByRole('alert')
    expect(alert).toHaveTextContent('Cut $8,000 of weekly spending by')
    expect(alert).toHaveTextContent('22/03/2027')
    expect(alert).toHaveTextContent('or you will lose the team')
    expect(alert).toHaveTextContent('Cut so far $2,000 of $10,000')
  })

  it('counts paydays when the deadline week is not declared yet', () => {
    show({ ...insolvent, deadline: null, paydays_left: 3 })

    render(<SolvencyBanner />)

    expect(screen.getByRole('alert')).toHaveTextContent('within 3 paydays')
  })

  it('says "payday" in the singular for the last one', () => {
    show({ ...insolvent, deadline: null, paydays_left: 1 })

    render(<SolvencyBanner />)

    expect(screen.getByRole('alert')).toHaveTextContent('within 1 payday or')
  })

  it('says the team is recovering once the weekly gap is closed', () => {
    show({ ...insolvent, shortfall: 0, paydays_left: null, deadline: null })

    render(<SolvencyBanner />)

    const alert = screen.getByRole('alert')
    expect(alert).toHaveTextContent('insolvent but recovering')
    expect(alert).not.toHaveTextContent('lose the team')
  })
})
