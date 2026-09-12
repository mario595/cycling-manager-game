import { useEffect, useState } from 'react'

import { getCalendar, type Calendar } from './api'

interface CalendarState {
  calendar: Calendar | null
  loading: boolean
  error: boolean
}

/**
 * Polls the calendar every 60s, same lifecycle as useSeason. No client-side
 * interpolation: nothing here changes between polls in a way worth
 * animating.
 */
export function useCalendar(): CalendarState {
  const [calendar, setCalendar] = useState<Calendar | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(false)

  useEffect(() => {
    let cancelled = false

    const fetchCalendar = () => {
      getCalendar()
        .then((data) => {
          if (cancelled) return
          setCalendar(data)
          setError(false)
          setLoading(false)
        })
        .catch(() => {
          if (cancelled) return
          setError(true)
          setLoading(false)
        })
    }

    fetchCalendar()
    const pollInterval = setInterval(fetchCalendar, 60_000)

    return () => {
      cancelled = true
      clearInterval(pollInterval)
    }
  }, [])

  return { calendar, loading, error }
}
