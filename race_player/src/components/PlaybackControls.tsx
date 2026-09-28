import { Button, Segmented, Space } from 'antd'
import {
  CaretRightOutlined,
  PauseOutlined,
  StepBackwardOutlined,
  StepForwardOutlined,
} from '@ant-design/icons'
import type { Wind } from '../types/race'
import { formatDuration } from '../utils/formatTime'
import { PLAYBACK_SPEEDS } from '../utils/usePlayback'
import WindCompass from './WindCompass'

// Re-exported for callers and tests that already reach for it here; the
// implementation moved to utils/formatTime.ts, where the game's replay
// screen imports it from (it must not pull antd in).
export { formatDuration }

const SPEEDS = PLAYBACK_SPEEDS.map((value) => ({ label: `x${value}`, value }))

interface PlaybackControlsProps {
  playing: boolean
  onTogglePlay: () => void
  tick: number
  maxTicks: number
  tickInterval: number
  speed: number
  onSpeedChange: (speed: number) => void
  onStep: (dir: -1 | 1) => void
  onSeek: (tick: number) => void
  wind?: Wind
}

export default function PlaybackControls({
  playing,
  onTogglePlay,
  tick,
  maxTicks,
  tickInterval,
  speed,
  onSpeedChange,
  onStep,
  onSeek,
  wind,
}: PlaybackControlsProps) {
  return (
    <div className="flex flex-col gap-2 p-3 bg-white rounded-lg border border-slate-200">
      <div className="flex items-center gap-3">
        <Space>
          <Button
            onClick={() => onStep(-1)}
            icon={<StepBackwardOutlined />}
            aria-label="Step back"
          />
          <Button
            type="primary"
            shape="circle"
            icon={playing ? <PauseOutlined /> : <CaretRightOutlined />}
            onClick={onTogglePlay}
            aria-label={playing ? 'Pause' : 'Play'}
          />
          <Button
            onClick={() => onStep(1)}
            icon={<StepForwardOutlined />}
            aria-label="Step forward"
          />
        </Space>

        <Segmented
          options={SPEEDS.map((s) => s.label)}
          value={`x${speed}`}
          onChange={(v) => onSpeedChange(Number(String(v).replace('x', '')))}
        />

        <div className="ml-auto flex items-center gap-3">
          <div className="flex flex-col items-end text-sm text-slate-500 tabular-nums">
            <span>{formatDuration(tick * tickInterval)} / {formatDuration(maxTicks * tickInterval)}</span>
            <span className="text-xs text-slate-400">tick {tick} / {maxTicks}</span>
          </div>
          <WindCompass wind={wind} />
        </div>
      </div>

      <input
        type="range"
        min={0}
        max={maxTicks}
        value={tick}
        onChange={(e) => onSeek(Number(e.target.value))}
        className="w-full accent-blue-600 cursor-pointer"
        aria-label="Seek"
      />
    </div>
  )
}
