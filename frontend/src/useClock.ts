import { useEffect, useRef, useState } from 'react'

import { getClock, type Clock } from './api'

interface ClockState {
  /** The game time right now, ticking forward client-side once a second
   * between server fetches. Null until the first fetch resolves. */
  now: Date | null
  loading: boolean
  error: boolean
}

/**
 * Polls the game clock every 60s — that stays the source of truth, since the
 * backend value only actually changes when a tick runs (hourly in
 * production). Polling, not a websocket: an hourly clock does not need a
 * socket, and a socket needs ASGI.
 *
 * Between polls, `now` is advanced client-side once a second by elapsed
 * real time, so a race that starts mid-session is visibly ticking rather
 * than frozen on the last fetched value. It resyncs to the server on every
 * poll, so client clock drift never compounds.
 */
export function useClock(): ClockState {
  const [clock, setClock] = useState<Clock | null>(null)
  const [now, setNow] = useState<Date | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(false)
  const fetchedAt = useRef<number | null>(null)

  useEffect(() => {
    let cancelled = false

    const fetchClock = () => {
      getClock()
        .then((data) => {
          if (cancelled) return
          setClock(data)
          fetchedAt.current = Date.now()
          setNow(new Date(data.current))
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
    const pollInterval = setInterval(fetchClock, 60_000)

    return () => {
      cancelled = true
      clearInterval(pollInterval)
    }
  }, [])

  useEffect(() => {
    if (!clock || fetchedAt.current === null) return

    const tickInterval = setInterval(() => {
      const elapsed = Date.now() - (fetchedAt.current ?? Date.now())
      setNow(new Date(new Date(clock.current).getTime() + elapsed))
    }, 1_000)

    return () => clearInterval(tickInterval)
  }, [clock])

  return { now, loading, error }
}
