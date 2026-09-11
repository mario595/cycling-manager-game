import { useNavigate } from 'react-router-dom'

import {
  Button,
  Card,
  CardHeader,
  PageBody,
  PageHeading,
  StatTile,
} from '../components/primitives'
import { buildProfile } from '../courseProfile'
import {
  DASHBOARD,
  FORM_WATCH,
  HEADLINE_STATS,
  INBOX,
  LEAGUE_TABLE,
  NEXT_RACE,
  RESULTS,
} from '../placeholderData'
import { seasonLabel } from '../seasonLabel'
import { color, font, formColor, inboxTag } from '../theme'
import { useSeason } from '../useSeason'

const profile = buildProfile(320, 74, 6)

export function Dashboard() {
  const navigate = useNavigate()
  const { position } = useSeason()

  return (
    <PageBody>
      <PageHeading
        eyebrow={seasonLabel(position)}
        title={DASHBOARD.greeting}
        subtitle={DASHBOARD.subtitle}
        aside={
          <>
            {HEADLINE_STATS.map((s) => (
              <StatTile key={s.key} label={s.key} value={s.value} suffix={s.suffix} />
            ))}
            <StatTile label="NEXT DEADLINE" value={DASHBOARD.deadline} dark />
          </>
        }
      />

      <ActionCards onWatchReplay={() => navigate('/race')} />

      <div
        style={{
          display: 'grid',
          gridTemplateColumns: 'repeat(auto-fit, minmax(320px, 1fr))',
          gap: 16,
          alignItems: 'start',
        }}
      >
        <LastNightsRaces />
        <NextRace />
        <DivisionTable />
        <FormWatch />
        <Inbox />
      </div>
    </PageBody>
  )
}

function ActionCards({ onWatchReplay }: { onWatchReplay: () => void }) {
  return (
    <div
      style={{
        display: 'grid',
        gridTemplateColumns: 'repeat(auto-fit, minmax(258px, 1fr))',
        gap: 14,
      }}
    >
      <div
        style={{
          background: color.accent,
          borderRadius: 14,
          padding: '18px 20px',
          display: 'flex',
          flexDirection: 'column',
          gap: 12,
        }}
      >
        <Eyebrow tone="dark">ACTION REQUIRED</Eyebrow>
        <CardTitle>
          Set your lineup for
          <br />
          Tour de Sancerre
        </CardTitle>
        <div style={{ fontSize: 12.5, color: '#3A2A1A' }}>
          6 of 8 slots filled · closes in 5h 42m
        </div>
        <Button style={{ marginTop: 2, alignSelf: 'flex-start' }}>Set lineup</Button>
      </div>

      <Card style={{ padding: '18px 20px', display: 'flex', flexDirection: 'column', gap: 12 }}>
        <Eyebrow>OVERNIGHT</Eyebrow>
        <CardTitle>
          2 results ready
          <br />
          to review
        </CardTitle>
        <div style={{ fontSize: 12.5, color: color.muted }}>
          GP de Verrières · Circuit d'Aubain
        </div>
        <Button
          variant="secondary"
          onClick={onWatchReplay}
          style={{ marginTop: 2, alignSelf: 'flex-start' }}
        >
          Watch replay
        </Button>
      </Card>

      <Card style={{ padding: '18px 20px', display: 'flex', flexDirection: 'column', gap: 12 }}>
        <Eyebrow>TRANSFER MARKET</Eyebrow>
        <CardTitle>
          2 bids awaiting
          <br />
          your response
        </CardTitle>
        <div style={{ fontSize: 12.5, color: color.muted }}>Highest: €340k for T. Okafor</div>
        <Button variant="secondary" style={{ marginTop: 2, alignSelf: 'flex-start' }}>
          Review bids
        </Button>
      </Card>
    </div>
  )
}

function Eyebrow({
  children,
  tone = 'light',
}: {
  children: React.ReactNode
  tone?: 'light' | 'dark'
}) {
  return (
    <div
      style={{
        fontSize: 10,
        letterSpacing: '1.4px',
        fontWeight: 600,
        color: tone === 'dark' ? color.ink : color.mutedStrong,
        fontFamily: font.mono,
      }}
    >
      {children}
    </div>
  )
}

function CardTitle({ children }: { children: React.ReactNode }) {
  return (
    <div style={{ fontSize: 17, fontWeight: 600, letterSpacing: '-0.3px', lineHeight: 1.25 }}>
      {children}
    </div>
  )
}

function LastNightsRaces() {
  return (
    <Card style={{ overflow: 'hidden', gridColumn: 'span 2' }}>
      <CardHeader
        title="Last night's races"
        action={
          <span style={{ fontSize: 12, color: color.accentInk, fontWeight: 500 }}>All results</span>
        }
      />
      <div style={{ display: 'flex', flexDirection: 'column' }}>
        {RESULTS.map((r, i) => {
          const won = r.pos === '1st'
          return (
            <div
              key={`${r.rider}-${i}`}
              style={{
                display: 'grid',
                gridTemplateColumns: '44px minmax(0,1.5fr) minmax(0,1fr) 70px',
                gap: 12,
                alignItems: 'center',
                padding: '13px 20px',
                borderBottom: `1px solid ${color.divider}`,
              }}
            >
              <div
                style={{
                  fontSize: 13,
                  fontWeight: 700,
                  fontFamily: font.mono,
                  color: won ? color.ink : color.muted,
                  background: won ? color.accent : color.canvas,
                  borderRadius: 7,
                  padding: '5px 0',
                  textAlign: 'center',
                }}
              >
                {r.pos}
              </div>
              <div style={{ display: 'flex', flexDirection: 'column', gap: 2, minWidth: 0 }}>
                <div style={{ fontSize: 14, fontWeight: 500, letterSpacing: '-0.1px', ...ellipsis }}>
                  {r.rider}
                </div>
                <div style={{ fontSize: 11.5, color: color.mutedStrong, fontFamily: font.mono }}>
                  {r.role}
                </div>
              </div>
              <div style={{ fontSize: 12.5, color: color.muted, ...ellipsis }}>{r.race}</div>
              <div
                style={{
                  textAlign: 'right',
                  fontSize: 13,
                  fontWeight: 600,
                  fontFamily: font.mono,
                  color: color.positive,
                }}
              >
                {r.pts}
              </div>
            </div>
          )
        })}
      </div>
    </Card>
  )
}

function NextRace() {
  const empty = NEXT_RACE.lineupSize - NEXT_RACE.lineup.length
  const slots = [...NEXT_RACE.lineup, ...Array<string>(empty).fill('+ empty')]

  return (
    <Card
      style={{ padding: '18px 20px', display: 'flex', flexDirection: 'column', gap: 14 }}
    >
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 10 }}>
        <div style={{ fontSize: 15, fontWeight: 600, letterSpacing: '-0.2px' }}>Next race</div>
        <div
          style={{
            fontSize: 10.5,
            background: color.canvas,
            borderRadius: 6,
            padding: '4px 8px',
            color: color.muted,
            fontFamily: font.mono,
          }}
        >
          {NEXT_RACE.countdown}
        </div>
      </div>

      <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
        <div style={{ fontSize: 19, fontWeight: 600, letterSpacing: '-0.4px' }}>{NEXT_RACE.name}</div>
        <div style={{ fontSize: 12.5, color: color.muted, fontFamily: font.mono }}>
          {NEXT_RACE.detail}
        </div>
      </div>

      <div style={{ background: color.canvas, borderRadius: 10, padding: '12px 12px 8px' }}>
        <svg
          viewBox="0 0 320 74"
          preserveAspectRatio="none"
          style={{ width: '100%', height: 74, display: 'block' }}
          role="img"
          aria-label={`Elevation profile for ${NEXT_RACE.name}`}
        >
          <polygon points={profile.polygon} fill="#E3E6EA" />
          <polyline points={profile.line} fill="none" stroke={color.ink} strokeWidth={1.5} />
        </svg>
      </div>

      <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
        <div style={{ fontSize: 11, letterSpacing: '1.2px', color: color.mutedStrong, fontFamily: font.mono }}>
          LINEUP {NEXT_RACE.lineup.length}/{NEXT_RACE.lineupSize}
        </div>
        <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>
          {slots.map((label, i) => {
            const isEmpty = label.startsWith('+')
            return (
              <div
                key={`${label}-${i}`}
                style={{
                  fontSize: 11.5,
                  padding: '5px 9px',
                  borderRadius: 7,
                  fontFamily: isEmpty ? font.mono : 'inherit',
                  background: isEmpty ? 'transparent' : color.canvas,
                  color: isEmpty ? '#666A72' : color.ink,
                  border: isEmpty ? '1px dashed #D6DAE0' : `1px solid ${color.dividerStrong}`,
                }}
              >
                {label}
              </div>
            )
          })}
        </div>
      </div>

      <Button style={{ padding: '10px 15px' }}>Complete lineup</Button>
    </Card>
  )
}

function DivisionTable() {
  return (
    <Card style={{ overflow: 'hidden' }}>
      <CardHeader
        title="Division 2"
        action={
          <span style={{ fontSize: 12, color: color.accentInk, fontWeight: 500 }}>Full table</span>
        }
      />
      {LEAGUE_TABLE.map((row) => (
        <div
          key={row.rank}
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: 12,
            padding: '11px 20px',
            borderBottom: `1px solid ${color.divider}`,
            background: row.me ? color.accentWash : 'transparent',
          }}
        >
          <div style={{ width: 20, fontSize: 12, color: color.mutedStrong, fontFamily: font.mono }}>
            {row.rank}
          </div>
          <div style={{ flex: 1, minWidth: 0, fontSize: 13.5, fontWeight: 500, ...ellipsis }}>
            {row.team}
          </div>
          <div style={{ fontSize: 13, fontWeight: 600, fontFamily: font.mono }}>{row.pts}</div>
        </div>
      ))}
    </Card>
  )
}

function FormWatch() {
  return (
    <Card style={{ overflow: 'hidden' }}>
      <div
        style={{
          padding: '16px 20px 13px',
          borderBottom: `1px solid ${color.dividerStrong}`,
          fontSize: 15,
          fontWeight: 600,
          letterSpacing: '-0.2px',
        }}
      >
        Form watch
      </div>
      {FORM_WATCH.map((f) => (
        <div
          key={f.name}
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: 12,
            padding: '12px 20px',
            borderBottom: `1px solid ${color.divider}`,
          }}
        >
          <div style={{ flex: 1, minWidth: 0, display: 'flex', flexDirection: 'column', gap: 2 }}>
            <div style={{ fontSize: 13.5, fontWeight: 500, ...ellipsis }}>{f.name}</div>
            <div style={{ fontSize: 11, color: color.mutedStrong, fontFamily: font.mono }}>
              {f.role}
            </div>
          </div>
          <div style={{ width: 76, flex: '0 0 76px', height: 6, background: color.track, borderRadius: 4, overflow: 'hidden' }}>
            <div style={{ width: `${f.value}%`, height: '100%', background: formColor(f.value) }} />
          </div>
          <div
            style={{
              width: 30,
              textAlign: 'right',
              fontSize: 12,
              fontWeight: 600,
              fontFamily: font.mono,
              color: f.delta.startsWith('+') ? color.positive : color.negative,
            }}
          >
            {f.delta}
          </div>
        </div>
      ))}
    </Card>
  )
}

function Inbox() {
  return (
    <Card style={{ overflow: 'hidden' }}>
      <CardHeader
        title="Inbox"
        action={
          <div
            style={{
              background: color.accent,
              color: color.ink,
              fontSize: 10,
              fontWeight: 700,
              padding: '2px 7px',
              borderRadius: 8,
              fontFamily: font.mono,
            }}
          >
            {INBOX.length}
          </div>
        }
      />
      {INBOX.map((m) => {
        const tag = inboxTag[m.tag]
        return (
          <div
            key={m.title}
            style={{
              display: 'flex',
              flexDirection: 'column',
              gap: 3,
              padding: '13px 20px',
              borderBottom: `1px solid ${color.divider}`,
            }}
          >
            <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
              <span
                style={{
                  fontSize: 9.5,
                  letterSpacing: '1.1px',
                  fontWeight: 700,
                  fontFamily: font.mono,
                  padding: '3px 6px',
                  borderRadius: 5,
                  background: tag.bg,
                  color: tag.fg,
                }}
              >
                {m.tag}
              </span>
              <span
                style={{
                  fontSize: 11,
                  color: '#666A72',
                  fontFamily: font.mono,
                  marginLeft: 'auto',
                }}
              >
                {m.time}
              </span>
            </div>
            <div style={{ fontSize: 13.5, fontWeight: 500, letterSpacing: '-0.1px' }}>{m.title}</div>
            <div style={{ fontSize: 12.5, color: color.muted, lineHeight: 1.4 }}>{m.body}</div>
          </div>
        )
      })}
    </Card>
  )
}

const ellipsis = {
  overflow: 'hidden',
  textOverflow: 'ellipsis',
  whiteSpace: 'nowrap',
} as const
