import { useEffect, useState } from 'react'

import { getSquad } from './api'

interface NextRaceSquadState {
  /** Whether the team chose a squad rather than accepting an auto-pick.
   * Null while unknown — a 403 (no team) or any failed request lands here,
   * and the Dashboard renders that as nothing. */
  saved: boolean | null
  loading: boolean
}

/**
 * Whether the team has chosen a squad for the next race. Unlike the polling
 * hooks it does not poll: squad status only changes when the manager changes
 * it on another screen, and coming back here remounts this hook.
 */
export function useNextRaceSquad(raceId: number | null): NextRaceSquadState {
  const [state, setState] = useState<NextRaceSquadState>({ saved: null, loading: false })

  useEffect(() => {
    if (raceId === null) {
      setState({ saved: null, loading: false })
      return
    }

    let cancelled = false
    setState({ saved: null, loading: true })

    getSquad(raceId)
      .then((squad) => {
        if (cancelled) return
        setState({ saved: squad.saved, loading: false })
      })
      .catch(() => {
        if (cancelled) return
        setState({ saved: null, loading: false })
      })

    return () => {
      cancelled = true
    }
  }, [raceId])

  return state
}