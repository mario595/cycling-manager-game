import { describe, expect, it } from 'vitest'

import { NAV_ITEMS, NAV_SECTIONS } from './navigation'

// The paths App.tsx maps to a real component. Every nav item must point at
// one of these — a nav item without a screen would open the catch-all.
const BUILT_SCREENS = new Set(['/', '/roster', '/staff', '/calendar', '/results', '/league'])

describe('navigation', () => {
  it('every nav item has a screen', () => {
    const missing = NAV_ITEMS.filter((item) => !BUILT_SCREENS.has(item.path))
    expect(missing).toEqual([])
  })

  it('no section is empty', () => {
    expect(NAV_SECTIONS.length).toBeGreaterThan(0)
    const empty = NAV_SECTIONS.filter((section) => section.items.length === 0)
    expect(empty).toEqual([])
  })

  it('no item declares a badge', () => {
    const withBadge = NAV_ITEMS.filter((item) => 'badge' in item)
    expect(withBadge).toEqual([])
  })
})