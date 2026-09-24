import { useEffect, useState } from 'react'

import { getRiderProfile, RiderNotFound, type RiderProfile } from './api'

interface RiderProfileState {
  profile: RiderProfile | null
  loading: boolean
  notFound: boolean
  error: boolean
}

/**
 * Fetches once on mount (and when riderId changes) — no polling, the same
 * cancelled-flag shape as useRaceDetail. `notFound` is a separate flag from
 * `error`: a 404 means the rider is gone (an expired free agent), which the
 * page must explain rather than show as a broken page. Changing riderId
 * resets all three flags so moving from one rider's page to another's does
 * not show the previous rider mid-load.
 */
export function useRiderProfile(riderId: number): RiderProfileState {
  const [profile, setProfile] = useState<RiderProfile | null>(null)
  const [loading, setLoading] = useState(true)
  const [notFound, setNotFound] = useState(false)
  const [error, setError] = useState(false)

  useEffect(() => {
    let cancelled = false
    setProfile(null)
    setLoading(true)
    setNotFound(false)
    setError(false)

    getRiderProfile(riderId)
      .then((data) => {
        if (cancelled) return
        setProfile(data)
        setLoading(false)
      })
      .catch((err) => {
        if (cancelled) return
        if (err instanceof RiderNotFound) {
          setNotFound(true)
        } else {
          setError(true)
        }
        setLoading(false)
      })

    return () => {
      cancelled = true
    }
  }, [riderId])

  return { profile, loading, notFound, error }
}
