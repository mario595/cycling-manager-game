import { useEffect, useState } from 'react'

import { parseRaceLog } from '../../race_player/src/utils/parseRaceLog'
import type { ParsedRace } from '../../race_player/src/types/race'
import { getRaceLog } from './api'

interface RaceLogState {
  race: ParsedRace | null
  loading: boolean
  error: boolean
}

/**
 * Fetches and parses a race's log once on mount (and when raceId changes) —
 * no polling; a finished race's log never changes.
 *
 * The parsing itself is race_player's, imported across like every other piece
 * of its logic (see frontend/README.md, "Conventions"). Gated by `enabled` for
 * the same reason as `useRaceResults`: while it is false the hook stays
 * settled and fires no request, and a request or a parse that fails is an
 * error state rather than a thrown render.
 */
export function useRaceLog(raceId: number, enabled: boolean): RaceLogState {
  const [race, setRace] = useState<ParsedRace | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(false)

  useEffect(() => {
    if (!enabled) {
      setRace(null)
      setLoading(false)
      setError(false)
      return
    }
    let cancelled = false
    setLoading(true)
    setError(false)

    getRaceLog(raceId)
      .then((text) => {
        if (cancelled) return
        setRace(parseRaceLog(text))
        setLoading(false)
      })
      .catch(() => {
        if (cancelled) return
        setError(true)
        setLoading(false)
      })

    return () => {
      cancelled = true
    }
  }, [raceId, enabled])

  return { race, loading, error }
}
