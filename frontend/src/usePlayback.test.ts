import { act, renderHook } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { usePlayback } from '../../race_player/src/utils/usePlayback'

/** The hook's key listener lives on window, so a test that dispatches one
 * has to say where the event was aimed: an event that reaches a control the
 * player is using must be left alone (D10). */
function press(key: string, target: EventTarget = window) {
  act(() => {
    target.dispatchEvent(new KeyboardEvent('keydown', { key, bubbles: true, cancelable: true }))
  })
}

describe('usePlayback', () => {
  beforeEach(() => {
    vi.useFakeTimers()
  })

  afterEach(() => {
    vi.useRealTimers()
  })

  it('advances one tick per tickInterval/speed while playing', () => {
    const { result } = renderHook(() => usePlayback(10, 2, { initialSpeed: 10 }))

    expect(result.current.playing).toBe(false)
    act(() => result.current.togglePlay())

    act(() => void vi.advanceTimersByTime(199))
    expect(result.current.tick).toBe(0)
    act(() => void vi.advanceTimersByTime(1))
    expect(result.current.tick).toBe(1)
  })

  it('stops at maxTicks and toggling at the end restarts from 0', () => {
    const { result } = renderHook(() => usePlayback(2, 1))
    act(() => result.current.togglePlay())

    act(() => void vi.advanceTimersByTime(3200))
    expect(result.current.tick).toBe(2)
    expect(result.current.playing).toBe(false)

    act(() => result.current.togglePlay())
    expect(result.current.tick).toBe(0)
    expect(result.current.playing).toBe(true)
  })

  it('seek clamps to [0, maxTicks]', () => {
    const { result } = renderHook(() => usePlayback(5, 1))

    act(() => result.current.seek(-3))
    expect(result.current.tick).toBe(0)
    act(() => result.current.seek(99))
    expect(result.current.tick).toBe(5)
  })

  it('space on a focused button does not toggle', () => {
    const { result } = renderHook(() => usePlayback(5, 1))
    const button = document.createElement('button')
    document.body.appendChild(button)

    press(' ', button)

    expect(result.current.playing).toBe(false)
    button.remove()
  })

  it('arrow keys step when focus is on the page body', () => {
    const { result } = renderHook(() => usePlayback(5, 1))
    act(() => result.current.seek(2))

    press('ArrowRight')
    expect(result.current.tick).toBe(3)
    press('ArrowLeft')
    expect(result.current.tick).toBe(2)
    press(' ')
    expect(result.current.playing).toBe(true)
  })
})
