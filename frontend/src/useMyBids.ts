import { useEffect, useRef, useState } from 'react'

import { getMyBids, type MyBidStatus } from './api'

interface MyBidsState {
  bids: MyBidStatus[]
  refresh: () => void
}

/**
 * Polls the caller's active bids every 30s so the outbid notice (spec
 * item 8) appears without a manual refresh. Starts as an empty list, not
 * null — "no active bids" is the common, normal state, not a loading
 * placeholder, so a failed or not-yet-returned fetch simply shows none.
 */
export function useMyBids(): MyBidsState {
  const [bids, setBids] = useState<MyBidStatus[]>([])
  const cancelledRef = useRef(false)

  const fetchBids = () => {
    getMyBids()
      .then((data) => {
        if (cancelledRef.current) return
        setBids(data)
      })
      .catch(() => {
        // Silent: the outbid notice is a courtesy, not the screen's main
        // content — a failed poll simply tries again in 30s.
      })
  }

  useEffect(() => {
    cancelledRef.current = false
    fetchBids()
    const pollInterval = setInterval(fetchBids, 30_000)

    return () => {
      cancelledRef.current = true
      clearInterval(pollInterval)
    }
  }, [])

  return { bids, refresh: fetchBids }
}
