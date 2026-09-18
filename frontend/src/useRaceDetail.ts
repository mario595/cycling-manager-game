import { useEffect, useState } from 'react'

import { getRaceDetail, type RaceDetail } from './api'

interface RaceDetailState {
  race: RaceDetail | null
  loading: boolean
  error: boolean
}

/**
 * Fetches once on mount (and when raceId changes) — no polling. Carries the
 * race's own facts: identity, status, when, how far and the course profile,
 * readable by any authenticated manager regardless of team.
 */
export function useRaceDetail(raceId: number): RaceDetailState {
  const [race, setRace] = useState<RaceDetail | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(false)

  useEffect(() => {
    let cancelled = false
    setLoading(true)
    setError(false)

    getRaceDetail(raceId)
      .then((data) => {
        if (cancelled) return
        setRace(data)
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
  }, [raceId])

  return { race, loading, error }
}