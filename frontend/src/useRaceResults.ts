import { useEffect, useState } from 'react'

import { getRaceResults, type RaceResults } from './api'

interface RaceResultsState {
  results: RaceResults | null
  loading: boolean
  error: boolean
}

/**
 * Fetches once on mount (and when raceId changes) — no polling. Gated by
 * `enabled`: while it is false the hook stays settled and non-loading and
 * fires no request, because the results endpoint 404s by design for a race
 * that has not finished and that failure must not surface as an error.
 */
export function useRaceResults(raceId: number, enabled: boolean): RaceResultsState {
  const [results, setResults] = useState<RaceResults | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(false)

  useEffect(() => {
    if (!enabled) {
      setResults(null)
      setLoading(false)
      setError(false)
      return
    }
    let cancelled = false
    setLoading(true)
    setError(false)

    getRaceResults(raceId)
      .then((data) => {
        if (cancelled) return
        setResults(data)
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

  return { results, loading, error }
}