/**
 * The sidebar navigation, straight from the design.
 *
 * This is the single source of truth for both the rail and the router: every
 * item has a real path, `App.tsx` generates a route per item, and anything
 * without a screen of its own yet lands on the shared placeholder. That is
 * deliberate — it means a new screen is wired up by pointing an existing nav
 * item at a component, and no link in the UI is ever dead.
 */

export interface NavItem {
  /** Route path, e.g. `/roster`. */
  path: string
  /** Label in the sidebar and the mobile top bar. */
  name: string
  /** Optional count pill, e.g. unread inbox messages. */
  badge?: string
}

export interface NavSection {
  label: string
  items: NavItem[]
}

export const NAV_SECTIONS: NavSection[] = [
  {
    label: 'HOME',
    items: [
      { path: '/', name: 'Dashboard' },
      { path: '/inbox', name: 'Inbox', badge: '3' },
    ],
  },
  {
    label: 'TEAM',
    items: [
      { path: '/roster', name: 'Roster' },
      { path: '/training', name: 'Training' },
      { path: '/tactics', name: 'Tactics' },
      { path: '/staff', name: 'Staff' },
    ],
  },
  {
    label: 'RACING',
    items: [
      { path: '/calendar', name: 'Calendar' },
      { path: '/race', name: 'Race day' },
      { path: '/results', name: 'Results' },
    ],
  },
  {
    label: 'MARKET',
    items: [
      { path: '/transfers', name: 'Transfers', badge: '2' },
      { path: '/scouting', name: 'Scouting' },
      { path: '/contracts', name: 'Contracts' },
    ],
  },
  {
    label: 'COMPETITION',
    items: [
      { path: '/league', name: 'League table' },
      { path: '/rankings', name: 'Rankings' },
    ],
  },
  {
    label: 'CLUB',
    items: [
      { path: '/finances', name: 'Finances' },
      { path: '/sponsors', name: 'Sponsors' },
      { path: '/facilities', name: 'Facilities' },
    ],
  },
]

/** Every nav item, flattened — used to build the routes. */
export const NAV_ITEMS: NavItem[] = NAV_SECTIONS.flatMap((s) => s.items)

/** The screen title shown in the mobile top bar. */
export function titleForPath(path: string): string {
  return NAV_ITEMS.find((i) => i.path === path)?.name ?? 'Dashboard'
}
