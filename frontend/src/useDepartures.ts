import { useEffect, useRef, useState } from 'react'

import { getDepartures, type Departure } from './api'

interface DeparturesState {
  /** Newest first. Null while loading or on error, never a fabricated
   * empty list: "nobody left" is a claim, and a failed fetch is not one. */
  departures: Departure[] | null
  loading: boolean
  error: boolean
}

/**
 * Polls the caller's team's departures every 60s (#158, #162), the same
 * lifecycle as useRoster. The whole history comes back; each screen filters
 * it with the helpers in departures.ts.
 */
export function useDepartures(): DeparturesState {
  const [departures, setDepartures] = useState<Departure[] | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(false)
  const cancelledRef = useRef(false)

  useEffect(() => {
    cancelledRef.current = false
    const fetchDepartures = () => {
      getDepartures()
        .then((data) => {
          if (cancelledRef.current) return
          setDepartures(data.departures)
          setError(false)
          setLoading(false)
        })
        .catch(() => {
          if (cancelledRef.current) return
          setError(true)
          setLoading(false)
        })
    }
    fetchDepartures()
    const pollInterval = setInterval(fetchDepartures, 60_000)

    return () => {
      cancelledRef.current = true
      clearInterval(pollInterval)
    }
  }, [])

  return { departures, loading, error }
}
