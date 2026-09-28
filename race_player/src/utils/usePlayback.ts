import { useCallback, useEffect, useRef, useState } from 'react'

export interface Playback {
  tick: number
  playing: boolean
  speed: number
  setSpeed: (speed: number) => void
  /** At maxTicks, rewinds to 0 and then plays. */
  togglePlay: () => void
  /** Clamped to [0, maxTicks]. */
  seek: (tick: number) => void
  step: (dir: -1 | 1) => void
}

export const PLAYBACK_SPEEDS = [1, 2, 5, 10, 25, 50] as const

const INTERACTIVE_TAGS = ['INPUT', 'TEXTAREA', 'SELECT', 'BUTTON']

/** Is this key event aimed at a control the player is operating? Space on a
 * focused button would otherwise toggle twice — the native click and this
 * handler — so nothing would appear to happen, and an arrow key on the
 * focused seek slider would step twice. */
function isInteractive(target: EventTarget | null): boolean {
  const element = target as HTMLElement | null
  if (!element) return false
  return element.isContentEditable || INTERACTIVE_TAGS.includes(element.tagName)
}

/** The playback loop, shared by every host so there is only one of them:
 * tick state, the play timer, speed, seek, step and the keyboard. `maxTicks`
 * and `tickInterval` come from the parsed race, and the starting speed from
 * the host — a five-hour stage is five hours at x1. */
export function usePlayback(
  maxTicks: number,
  tickInterval: number,
  options?: { initialSpeed?: number },
): Playback {
  const [tick, setTick] = useState(0)
  const [playing, setPlaying] = useState(false)
  const [speed, setSpeed] = useState(options?.initialSpeed ?? 1)

  const tickRef = useRef(tick)
  tickRef.current = tick

  useEffect(() => {
    if (!playing) return
    const interval = setInterval(() => {
      setTick((t) => {
        if (t >= maxTicks) {
          setPlaying(false)
          return t
        }
        return t + 1
      })
    }, (1000 * tickInterval) / speed)
    return () => clearInterval(interval)
  }, [playing, speed, maxTicks, tickInterval])

  const togglePlay = useCallback(() => {
    if (tickRef.current >= maxTicks) setTick(0)
    setPlaying((p) => !p)
  }, [maxTicks])

  const seek = useCallback(
    (t: number) => setTick(Math.max(0, Math.min(maxTicks, t))),
    [maxTicks],
  )

  const step = useCallback(
    (dir: -1 | 1) => {
      seek(tickRef.current + dir)
    },
    [seek],
  )

  // Stable refs so the key listener never needs re-subscribing.
  const stepRef = useRef(step)
  stepRef.current = step
  const togglePlayRef = useRef(togglePlay)
  togglePlayRef.current = togglePlay

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (isInteractive(e.target)) return
      if (e.key === 'ArrowLeft') {
        e.preventDefault()
        stepRef.current(-1)
      } else if (e.key === 'ArrowRight') {
        e.preventDefault()
        stepRef.current(1)
      } else if (e.key === ' ') {
        e.preventDefault()
        togglePlayRef.current()
      }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [])

  return { tick, playing, speed, setSpeed, togglePlay, seek, step }
}
