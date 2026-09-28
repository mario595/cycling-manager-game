import { describe, expect, it } from 'vitest'

import { parseRaceLog } from './parseRaceLog'

const HEADER = {
  v: 1,
  tick_interval: 2,
  course_length: 500,
  segments: [{ length: 500, gradient: 0 }],
  teams: { t1: { code: 'ALP', name: 'Alpine Racing' } },
  riders: [
    { id: 'gc1', name: 'GC Climber 1', team: 't1', role: 'leader' },
    { id: 'sp2', name: 'SP Sprint 2', team: 't1', role: 'support' },
  ],
  wind_band: 'moderate',
}

function fixture(header: unknown = HEADER, samples: unknown[] = [SAMPLE]): string {
  return [JSON.stringify(header), ...samples.map((s) => JSON.stringify(s))].join('\n') + '\n'
}

const SAMPLE = [0, [
  [0.0, 8.5, 93.4, 97.1, 0, null],
  [3.2, 8.5, 93.2, 97.0, 3, null],
], [17.3, 214.6]]

describe('parseRaceLog', () => {
  it('decodes samples into full riders with identity from the header', () => {
    const race = parseRaceLog(fixture())
    expect(race.snapshots).toHaveLength(1)
    const riders = race.snapshots[0].riders
    expect(riders[0].name).toBe('GC Climber 1')
    expect(riders[0].team).toBe('t1')
    expect(riders[0].role).toBe('leader')
    expect(riders[1].name).toBe('SP Sprint 2')
    expect(riders[1].team).toBe('t1')
    expect(riders[1].pos).toBe(3.2)
    expect(riders[1].speed).toBe(8.5)
    expect(riders[1].energy).toBe(93.2)
    expect(riders[1].stamina).toBe(97.0)
  })

  it('decodes the flags bitmask into the rider booleans', () => {
    const race = parseRaceLog(fixture())
    const [first, second] = race.snapshots[0].riders
    expect(first.pulling).toBe(false)
    expect(first.surging).toBe(false)
    expect(first.finished).toBe(false)
    expect(second.pulling).toBe(true)
    expect(second.surging).toBe(true)
    expect(second.finished).toBe(false)
  })

  it('decodes the dnf flag (bit 8)', () => {
    const cut = [0, [
      [100.0, 0.0, 40.0, 20.0, 8, null],
      [120.0, 9.0, 80.0, 70.0, 4, 4000.0],
    ]]
    const race = parseRaceLog(fixture(HEADER, [cut]))
    const [cutRider, finisher] = race.snapshots[0].riders
    expect(cutRider.dnf).toBe(true)
    expect(cutRider.finished).toBe(false)
    expect(finisher.dnf).toBe(false)
  })

  it('surfaces tickInterval alongside maxTicks and the header-wide fields', () => {
    const race = parseRaceLog(fixture())
    expect(race.tickInterval).toBe(2)
    expect(race.maxTicks).toBe(0)
    expect(race.courseLength).toBe(500)
    expect(race.teamCodes).toEqual({ t1: 'ALP' })
    expect(race.teamNames).toEqual({ t1: 'Alpine Racing' })
    expect(race.snapshots[0].wind).toEqual({
      speed: 17.3,
      angle: 214.6,
      band: 'moderate',
    })
  })

  it('omits wind entirely when the header has no wind_band', () => {
    const { wind_band: _band, ...noWind } = HEADER
    const singleRider = { ...HEADER, riders: [HEADER.riders[0]] }
    const sample = [0, [[0.0, 8.5, 93.4, 97.1, 0, null]]]
    const race = parseRaceLog(fixture({ ...noWind, riders: singleRider.riders }, [sample]))
    expect(race.snapshots[0].wind).toBeUndefined()
  })

  it('throws on an unsupported format version', () => {
    expect(() => parseRaceLog(fixture({ ...HEADER, v: 2 }))).toThrow(/v2 is not supported/)
  })

  it('throws when line 1 is a sample rather than a header', () => {
    expect(() => parseRaceLog(fixture([0, [[0.0, 8.5, 93.4, 97.1, 0, null]]]))).toThrow(/no header/)
  })

  it('throws on an empty file', () => {
    expect(() => parseRaceLog('')).toThrow(/empty/)
  })
})