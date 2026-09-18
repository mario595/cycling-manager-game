/**
 * The sidebar navigation, straight from the design.
 *
 * This is the single source of truth for both the rail and the router: every
 * item has a real path and `App.tsx` generates a route per item. Only items
 * with a built screen appear here — a feature that does not exist yet is not
 * hinted at, and a future screen is wired up by adding its item.
 */

export interface NavItem {
  /** Route path, e.g. `/roster`. */
  path: string
  /** Label in the sidebar and the mobile top bar. */
  name: string
}

export interface NavSection {
  label: string
  items: NavItem[]
}

export const NAV_SECTIONS: NavSection[] = [
  {
    label: 'HOME',
    items: [{ path: '/', name: 'Dashboard' }],
  },
  {
    label: 'TEAM',
    items: [
      { path: '/roster', name: 'Roster' },
      { path: '/staff', name: 'Staff' },
      { path: '/finances', name: 'Finances' },
    ],
  },
  {
    label: 'RACING',
    items: [
      { path: '/calendar', name: 'Calendar' },
      { path: '/results', name: 'Results' },
    ],
  },
  {
    label: 'COMPETITION',
    items: [{ path: '/league', name: 'League table' }],
  },
]

/** Every nav item, flattened — used to build the routes. */
export const NAV_ITEMS: NavItem[] = NAV_SECTIONS.flatMap((s) => s.items)

/** The screen title shown in the mobile top bar. */
export function titleForPath(path: string): string {
  return NAV_ITEMS.find((i) => i.path === path)?.name ?? 'Dashboard'
}
