import { BrowserRouter, Route, Routes } from 'react-router-dom'

import { Layout } from './components/Layout'
import { NAV_ITEMS } from './navigation'
import { Calendar } from './screens/Calendar'
import { ClaimTeam } from './screens/ClaimTeam'
import { Dashboard } from './screens/Dashboard'
import { Login } from './screens/Login'
import { Placeholder } from './screens/Placeholder'
import { Race } from './screens/Race'
import { Register } from './screens/Register'
import { Roster } from './screens/Roster'
import { AuthProvider } from './useAuth'

/**
 * Screens that are actually built. Every other nav item gets the placeholder,
 * which is what keeps the sidebar honest: adding a screen here is the only
 * step needed to replace its placeholder.
 */
const SCREENS: Record<string, React.ComponentType> = {
  '/': Dashboard,
  '/roster': Roster,
  '/calendar': Calendar,
}

export function App() {
  return (
    <BrowserRouter>
      <AuthProvider>
        <Routes>
          <Route element={<Layout />}>
            {NAV_ITEMS.map((item) => {
              const Screen = SCREENS[item.path] ?? Placeholder
              // '/' is the layout's index route; the rest are plain paths.
              return item.path === '/' ? (
                <Route key={item.path} index element={<Screen />} />
              ) : (
                <Route key={item.path} path={item.path} element={<Screen />} />
              )
            })}
            {/* Parameterised, so it doesn't fit the path -> component map
                above — the /race nav item itself still lands on Placeholder. */}
            <Route path="/race/:raceId" element={<Race />} />
            {/* Not nav items, same reason /race/:raceId isn't — they must
                not appear in the sidebar. */}
            <Route path="/login" element={<Login />} />
            <Route path="/register" element={<Register />} />
            <Route path="/claim" element={<ClaimTeam />} />
            {/* Anything outside the nav — a stale bookmark, a typo — still gets
                the chrome rather than a blank page. */}
            <Route path="*" element={<Placeholder />} />
          </Route>
        </Routes>
      </AuthProvider>
    </BrowserRouter>
  )
}
