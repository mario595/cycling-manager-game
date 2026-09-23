import { describe, expect, it } from 'vitest'

import { formatDuration } from './PlaybackControls'

describe('formatDuration (race seconds)', () => {
  it('renders ticks as real seconds', () => {
    expect(formatDuration(124)).toBe('0h 2m 4s')
    expect(formatDuration(45)).toBe('0h 0m 45s')
    expect(formatDuration(3600)).toBe('1h 0m 0s')
  })

  it('weights samples by tickInterval: 62 samples at 2s spans 2m 2s, not 1m 1s', () => {
    const maxTicks = 62 - 1
    const tickInterval = 2
    expect(formatDuration(maxTicks * tickInterval)).toBe('0h 2m 2s')
  })
})