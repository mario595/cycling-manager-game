import { useEffect, useState } from 'react'

import { getClock, type Clock } from './api'

interface ClockState {
  clock: Clock | null
  loading: boolean
  error: boolean
}

/**
 * Polls the game clock every 60s. Polling, not a websocket: an hourly clock
 * does not need a socket, and a socket needs ASGI.
 */
export function useClock(): ClockState {
  const [clock, setClock] = useState<Clock | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(false)

  useEffect(() => {
    let cancelled = false

    const fetchClock = () => {
      getClock()
        .then((data) => {
          if (cancelled) return
          setClock(data)
          setError(false)
          setLoading(false)
        })
        .catch(() => {
          if (cancelled) return
          setError(true)
          setLoading(false)
        })
    }

    fetchClock()
    const interval = setInterval(fetchClock, 60_000)

    return () => {
      cancelled = true
      clearInterval(interval)
    }
  }, [])

  return { clock, loading, error }
}
