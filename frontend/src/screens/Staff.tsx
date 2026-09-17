import { useState } from 'react'

import { fireTrainer, hireTrainer, type Trainer } from '../api'
import { Bar, Button, Card, PageBody, PageHeading } from '../components/primitives'
import { barColor, color, font } from '../theme'
import { useAuth } from '../useAuth'
import { useStaff } from '../useStaff'

type SkillKey = 'climb' | 'sprint' | 'flat' | 'resistance' | 'positioning'

const SKILL_LABELS: { key: SkillKey; label: string }[] = [
  { key: 'climb', label: 'Climbing' },
  { key: 'sprint', label: 'Sprinting' },
  { key: 'flat', label: 'Flat' },
  { key: 'resistance', label: 'Resistance' },
  { key: 'positioning', label: 'Positioning' },
]

export function Staff() {
  const { me, loading: authLoading } = useAuth()
  const hasTeam = me?.team != null

  const { staff, loading, error, refresh } = useStaff()
  const [actionError, setActionError] = useState<string | null>(null)
  const [pending, setPending] = useState(false)

  if (authLoading || loading) return null

  if (!hasTeam) {
    return (
      <PageBody gap={18} paddingTop={26}>
        <Card style={{ padding: '18px 20px' }}>
          <div style={{ fontSize: 13.5, color: color.muted }}>
            You do not manage a team, so there is no staff to show here.
          </div>
        </Card>
      </PageBody>
    )
  }

  if (error || !staff) {
    return (
      <PageBody gap={18} paddingTop={26}>
        <Card style={{ padding: '18px 20px' }}>
          <div style={{ fontSize: 13.5, color: color.muted }}>Couldn't load staff.</div>
        </Card>
      </PageBody>
    )
  }

  const handleHire = async (trainerId: number) => {
    setPending(true)
    setActionError(null)
    try {
      await hireTrainer(trainerId)
      refresh()
    } catch (err) {
      setActionError(err instanceof Error ? err.message : 'Could not hire that trainer.')
    } finally {
      setPending(false)
    }
  }

  const handleFire = async () => {
    setPending(true)
    setActionError(null)
    try {
      await fireTrainer()
      refresh()
    } catch (err) {
      setActionError(err instanceof Error ? err.message : 'Could not fire your trainer.')
    } finally {
      setPending(false)
    }
  }

  return (
    <PageBody gap={18} paddingTop={26}>
      <PageHeading
        eyebrow="TEAM · STAFF"
        title="Staff"
        titleSize={29}
        subtitle={
          staff.trainer
            ? 'Your trainer improves riders fastest in their speciality.'
            : 'Hire a trainer from the pool below — it is free.'
        }
      />

      {actionError ? (
        <Card style={{ padding: '12px 16px', borderColor: '#D9534F' }}>
          <div style={{ fontSize: 13, color: '#D9534F' }}>{actionError}</div>
        </Card>
      ) : null}

      {staff.trainer ? (
        <TrainerCard trainer={staff.trainer} action={<Button onClick={handleFire} style={{ opacity: pending ? 0.6 : 1 }}>Fire</Button>} />
      ) : (
        <div
          style={{
            display: 'grid',
            gridTemplateColumns: 'repeat(auto-fill, minmax(288px, 1fr))',
            gap: 12,
          }}
        >
          {staff.pool.map((trainer) => (
            <TrainerCard
              key={trainer.id}
              trainer={trainer}
              action={
                <Button onClick={() => handleHire(trainer.id)} style={{ opacity: pending ? 0.6 : 1 }}>
                  Hire
                </Button>
              }
            />
          ))}
        </div>
      )}
    </PageBody>
  )
}

function TrainerCard({ trainer, action }: { trainer: Trainer; action: React.ReactNode }) {
  return (
    <Card style={{ padding: '15px 16px', display: 'flex', flexDirection: 'column', gap: 12 }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
        <div
          style={{
            width: 40,
            height: 40,
            borderRadius: 11,
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            fontSize: 14,
            fontWeight: 700,
            fontFamily: font.mono,
            background: color.canvas,
            color: color.ink,
            flex: '0 0 40px',
          }}
        >
          {trainer.speciality.slice(0, 2).toUpperCase()}
        </div>
        <div style={{ flex: 1, minWidth: 0, display: 'flex', flexDirection: 'column', gap: 3 }}>
          <div
            style={{
              fontSize: 14.5,
              fontWeight: 600,
              letterSpacing: '-0.2px',
              overflow: 'hidden',
              textOverflow: 'ellipsis',
              whiteSpace: 'nowrap',
            }}
          >
            {trainer.name}
          </div>
          <div style={{ fontSize: 11, color: color.mutedStrong, fontFamily: font.mono }}>
            {trainer.speciality.toUpperCase()} SPECIALIST
          </div>
        </div>
        {action}
      </div>

      <div style={{ display: 'flex', flexDirection: 'column', gap: 9 }}>
        {SKILL_LABELS.map(({ key, label }) => {
          const value = trainer.skills[key]
          return (
            <div key={key} style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
              <span style={{ width: 88, flex: '0 0 88px', fontSize: 12.5, color: '#565A61' }}>
                {label}
              </span>
              <Bar value={value * 10} fill={barColor(value * 10)} height={6} />
              <span
                style={{
                  width: 20,
                  textAlign: 'right',
                  fontSize: 12,
                  fontWeight: 600,
                  fontFamily: font.mono,
                }}
              >
                {value}
              </span>
            </div>
          )
        })}
      </div>
    </Card>
  )
}
