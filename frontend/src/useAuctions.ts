import { useEffect, useRef, useState } from 'react'

import { getAuctions, type AuctionMarket } from './api'

interface AuctionsState {
  market: AuctionMarket | null
  loading: boolean
  error: boolean
  refresh: () => void
}

/**
 * Polls the auction market every 30s — shorter than useFreeAgents' 60s,
 * since a bid can land at any moment and a stale current price is more
 * misleading here than in the free-agent pool. Renders nothing while
 * loading or on error, the same discipline useFreeAgents established.
 *
 * Exposes refresh() so the screen can re-fetch right after listing a
 * rider or placing a bid instead of waiting for the next poll.
 */
export function useAuctions(): AuctionsState {
  const [market, setMarket] = useState<AuctionMarket | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(false)
  const cancelledRef = useRef(false)

  const fetchMarket = () => {
    getAuctions()
      .then((data) => {
        if (cancelledRef.current) return
        setMarket(data)
        setError(false)
        setLoading(false)
      })
      .catch(() => {
        if (cancelledRef.current) return
        setError(true)
        setLoading(false)
      })
  }

  useEffect(() => {
    cancelledRef.current = false
    fetchMarket()
    const pollInterval = setInterval(fetchMarket, 30_000)

    return () => {
      cancelledRef.current = true
      clearInterval(pollInterval)
    }
  }, [])

  return { market, loading, error, refresh: fetchMarket }
}
