import { useState } from 'react'
import { Link } from 'react-router-dom'

import { setTrainingFocus, type TrainingChange } from '../api'
import { Button, Card, CardHeader, PageBody, PageHeading } from '../components/primitives'
import { color, font } from '../theme'
import { useAuth } from '../useAuth'
import { useTraining } from '../useTraining'

const FOCUS_LABELS: Record<string, string> = {
  climb: 'Climbing',
  sprint: 'Sprinting',
  flat: 'Flat',
  resistance: 'Resistance',
  positioning: 'Positioning',
}

export function Training() {
  const { me, loading: authLoading } = useAuth()
  const hasTeam = me?.team != null

  const { training, loading, error, refresh } = useTraining()
  const [actionError, setActionError] = useState<string | null>(null)
  const [pending, setPending] = useState<string | null>(null)

  if (authLoading || loading) return null

  if (!hasTeam) {
    return (
      <PageBody gap={18} paddingTop={26}>
        <Card style={{ padding: '18px 20px' }}>
          <div style={{ fontSize: 13.5, color: color.muted }}>
            You do not manage a team, so there is nothing to train here.
          </div>
        </Card>
      </PageBody>
    )
  }

  if (error || !training) {
    return (
      <PageBody gap={18} paddingTop={26}>
        <Card style={{ padding: '18px 20px' }}>
          <div style={{ fontSize: 13.5, color: color.muted }}>Couldn't load training.</div>
        </Card>
      </PageBody>
    )
  }

  const handleFocus = async (attribute: string) => {
    setPending(attribute)
    setActionError(null)
    try {
      await setTrainingFocus(attribute)
      refresh()
    } catch (err) {
      setActionError(err instanceof Error ? err.message : 'Could not set that focus.')
    } finally {
      setPending(null)
    }
  }

  return (
    <PageBody gap={18} paddingTop={26}>
      <PageHeading
        eyebrow="TEAM · TRAINING"
        title="Training"
        titleSize={29}
        subtitle={
          training.has_trainer
            ? 'Your trainer steers your riders towards one focus attribute each week.'
            : 'Hire a trainer to start weekly training. It is free.'
        }
      />

      {actionError ? (
        <Card style={{ padding: '12px 16px', borderColor: '#D9534F' }}>
          <div style={{ fontSize: 13, color: '#D9534F' }}>{actionError}</div>
        </Card>
      ) : null}

      {training.last_week ? (
        <LastWeekCard changes={training.last_week.changes} attribute={training.last_week.attribute} />
      ) : null}

      {training.has_trainer ? (
        <Card>
          <CardHeader title="Weekly focus" />
          <div style={{ padding: '16px 20px', display: 'flex', flexWrap: 'wrap', gap: 10 }}>
            {training.options.map((option) => (
              <Button
                key={option}
                variant={option === training.focus ? 'primary' : 'secondary'}
                onClick={() => handleFocus(option)}
                style={{ opacity: pending === option || (pending && pending !== option) ? 0.6 : 1 }}
              >
                {FOCUS_LABELS[option] ?? option}
              </Button>
            ))}
          </div>
        </Card>
      ) : (
        <Card style={{ padding: '18px 20px' }}>
          <div style={{ fontSize: 13.5, color: color.muted }}>
            A trainer decides what to focus on. <Link to="/staff" style={{ color: color.accentInk }}>Go to Staff</Link> to hire one.
          </div>
        </Card>
      )}
    </PageBody>
  )
}

function LastWeekCard({ changes, attribute }: { changes: TrainingChange[]; attribute: string }) {
  return (
    <Card>
      <CardHeader
        title="Last week"
        action={
          <div style={{ fontSize: 11, letterSpacing: '0.8px', color: color.mutedStrong, fontFamily: font.mono }}>
            {(FOCUS_LABELS[attribute] ?? attribute).toUpperCase()} FOCUS
          </div>
        }
      />
      {changes.length === 0 ? (
        <div style={{ padding: '18px 20px', fontSize: 13.5, color: color.muted }}>
          No visible changes last week.
        </div>
      ) : (
        changes.map((change) => (
          <div
            key={change.rider_id}
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: 12,
              padding: '11px 20px',
              borderTop: `1px solid ${color.dividerStrong}`,
            }}
          >
            <div
              style={{
                flex: 1,
                minWidth: 0,
                fontSize: 14,
                fontWeight: 600,
                letterSpacing: '-0.2px',
                overflow: 'hidden',
                textOverflow: 'ellipsis',
                whiteSpace: 'nowrap',
              }}
            >
              {change.rider_name}
            </div>
            <div style={{ fontSize: 11.5, color: color.mutedStrong, fontFamily: font.mono }}>
              {(FOCUS_LABELS[change.attribute] ?? change.attribute).toUpperCase()}
            </div>
            <div style={{ fontSize: 13, fontFamily: font.mono, whiteSpace: 'nowrap' }}>
              <span style={{ color: color.muted }}>{change.from_value}</span>
              <span style={{ color: color.accentInk, padding: '0 5px' }}>→</span>
              <span style={{ fontWeight: 600 }}>{change.to_value}</span>
            </div>
          </div>
        ))
      )}
    </Card>
  )
}