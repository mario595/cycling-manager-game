import { useEffect, useState } from 'react'

import { getPosition, type Position } from './api'

interface SeasonState {
  position: Position | null
  loading: boolean
  error: boolean
}

/**
 * Polls the season position every 60s, same lifecycle as useClock. Unlike
 * the clock there is no client-side interpolation: the week number does not
 * visibly tick between polls, so there is nothing to interpolate.
 */
export function useSeason(): SeasonState {
  const [position, setPosition] = useState<Position | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(false)

  useEffect(() => {
    let cancelled = false

    const fetchPosition = () => {
      getPosition()
        .then((data) => {
          if (cancelled) return
          setPosition(data)
          setError(false)
          setLoading(false)
        })
        .catch(() => {
          if (cancelled) return
          setError(true)
          setLoading(false)
        })
    }

    fetchPosition()
    const pollInterval = setInterval(fetchPosition, 60_000)

    return () => {
      cancelled = true
      clearInterval(pollInterval)
    }
  }, [])

  return { position, loading, error }
}
