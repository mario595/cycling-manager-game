import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom'

import { Layout } from './components/Layout'
import { NAV_ITEMS } from './navigation'
import { Calendar } from './screens/Calendar'
import { ClaimTeam } from './screens/ClaimTeam'
import { Dashboard } from './screens/Dashboard'
import { Finances } from './screens/Finances'
import { League } from './screens/League'
import { Login } from './screens/Login'
import { Race } from './screens/Race'
import { Register } from './screens/Register'
import { RiderProfile } from './screens/RiderProfile'
import { Roster } from './screens/Roster'
import { Sponsors } from './screens/Sponsors'
import { Staff } from './screens/Staff'
import { Training } from './screens/Training'
import { Transfers } from './screens/Transfers'
import { AuthProvider } from './useAuth'

/**
 * Screens that are actually built, keyed by nav path. `navigation.ts` is the
 * single source of truth for the sidebar and the router both, so this map is
 * the bridge between the two: every nav item must resolve here, and an
 * unknown path falls through to the catch-all below.
 */
const SCREENS: Record<string, React.ComponentType> = {
  '/': Dashboard,
  '/roster': Roster,
  '/training': Training,
  '/staff': Staff,
  '/sponsors': Sponsors,
  '/finances': Finances,
  '/calendar': Calendar,
  '/transfers': Transfers,
  '/league': League,
}

export function App() {
  return (
    <BrowserRouter>
      <AuthProvider>
        <Routes>
          <Route element={<Layout />}>
            {NAV_ITEMS.map((item) => {
              const Screen = SCREENS[item.path]
              // '/' is the layout's index route; the rest are plain paths.
              return item.path === '/' ? (
                <Route key={item.path} index element={<Screen />} />
              ) : (
                <Route key={item.path} path={item.path} element={<Screen />} />
              )
            })}
            {/* Parameterised, so it doesn't fit the path -> component map
                above — reached only by clicking a race on the calendar. */}
            <Route path="/race/:raceId" element={<Race />} />
            {/* Parameterised, same reason /race/:raceId is — reached from
                the Roster panel, a race result row or a free-agent card. */}
            <Route path="/riders/:riderId" element={<RiderProfile />} />
            {/* Not nav items, same reason /race/:raceId isn't — they must
                not appear in the sidebar. */}
            <Route path="/login" element={<Login />} />
            <Route path="/register" element={<Register />} />
            <Route path="/claim" element={<ClaimTeam />} />
            {/* Anything outside the nav — a stale bookmark, a typo — goes
                home. It stays inside the Layout route so an unknown path
                still passes through the session and team guards: a logged-out
                visitor typing /rostr must reach /login, not the
                dashboard. */}
            <Route path="*" element={<Navigate to="/" replace />} />
          </Route>
        </Routes>
      </AuthProvider>
    </BrowserRouter>
  )
}