import { describe, expect, it } from 'vitest'

import { NAV_ITEMS, NAV_SECTIONS, racePath, replayPath, riderPath, titleForPath } from './navigation'

// The paths App.tsx maps to a real component. Every nav item must point at
// one of these — a nav item without a screen would open the catch-all.
const BUILT_SCREENS = new Set([
  '/',
  '/roster',
  '/training',
  '/staff',
  '/development-squad',
  '/sponsors',
  '/finances',
  '/calendar',
  '/league',
  '/transfers',
])

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

  it('riderPath builds a stable link', () => {
    expect(riderPath(7)).toBe('/riders/7')
  })

  it('titleForPath returns Rider for a rider page', () => {
    expect(titleForPath('/riders/7')).toBe('Rider')
  })

  it('builds race and replay links', () => {
    expect(racePath(7)).toBe('/race/7')
    expect(replayPath(7)).toBe('/race/7/replay')
  })

  it('titleForPath names both race screens', () => {
    expect(titleForPath('/race/7')).toBe('Race')
    expect(titleForPath('/race/7/replay')).toBe('Replay')
  })
})