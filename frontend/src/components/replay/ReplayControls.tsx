import { PLAYBACK_SPEEDS, type Playback } from '../../../../race_player/src/utils/usePlayback'
import { formatDuration } from '../../../../race_player/src/utils/formatTime'
import type { Wind } from '../../../../race_player/src/types/race'
import WindCompass from '../../../../race_player/src/components/WindCompass'

import { color, font } from '../../theme'
import { Button, Card, Chip } from '../primitives'

/**
 * The game's playback bar: the same six speeds and the same stepping the
 * standalone viewer has, with the clock written in the game's own type and
 * the wind read-out race_player already draws.
 *
 * `tick` is an index into the log's snapshots, not a time — the elapsed
 * reading multiplies it by the log's own `tickInterval`, so a race recorded
 * on a different tick length still reads correctly.
 */
export function ReplayControls({
  playback,
  tickInterval,
  maxTicks,
  wind,
}: {
  playback: Playback
  tickInterval: number
  maxTicks: number
  wind?: Wind
}) {
  const { playing, speed, tick, togglePlay, step, seek, setSpeed } = playback

  return (
    <Card style={{ padding: '14px 18px', display: 'flex', flexDirection: 'column', gap: 12 }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 10, flexWrap: 'wrap' }}>
        <Button variant="secondary" onClick={() => step(-1)} ariaLabel="Step back">
          ◀◀
        </Button>
        <Button variant="primary" onClick={togglePlay} ariaLabel={playing ? 'Pause' : 'Play'}>
          {playing ? '❚❚' : '▶'}
        </Button>
        <Button variant="secondary" onClick={() => step(1)} ariaLabel="Step forward">
          ▶▶
        </Button>

        <div style={{ display: 'flex', gap: 6, marginLeft: 4 }}>
          {PLAYBACK_SPEEDS.map((value) => (
            <Chip key={value} active={speed === value} onClick={() => setSpeed(value)}>
              ×{value}
            </Chip>
          ))}
        </div>

        <div
          style={{
            marginLeft: 'auto',
            display: 'flex',
            alignItems: 'center',
            gap: 14,
          }}
        >
          <div style={{ fontFamily: font.mono, fontSize: 13, color: color.mutedStrong }}>
            {formatDuration(tick * tickInterval)} / {formatDuration(maxTicks * tickInterval)}
          </div>
          {wind ? <WindCompass wind={wind} /> : null}
        </div>
      </div>

      <input
        type="range"
        aria-label="Seek"
        min={0}
        max={maxTicks}
        value={tick}
        onChange={(e) => seek(Number(e.target.value))}
        style={{ width: '100%', accentColor: color.ink }}
      />
    </Card>
  )
}
