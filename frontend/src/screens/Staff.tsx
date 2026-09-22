import { useMemo, useState } from 'react'

import { fireTrainer, hireTrainer, type Trainer } from '../api'
import { Bar, Button, Card, Chip, ChipLabel, PageBody, PageHeading } from '../components/primitives'
import { formatMoney } from '../format'
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

type SortKey = 'hire_fee' | 'weekly_salary' | 'name' | SkillKey

const SORT_OPTIONS: Array<{ key: SortKey; label: string }> = [
  { key: 'hire_fee', label: 'Fee' },
  { key: 'weekly_salary', label: 'Salary' },
  { key: 'name', label: 'Name' },
  ...SKILL_LABELS,
]

export function Staff() {
  const { me, loading: authLoading } = useAuth()
  const hasTeam = me?.team != null

  const { staff, loading, error, refresh } = useStaff()
  const [actionError, setActionError] = useState<string | null>(null)
  const [pending, setPending] = useState(false)
  const [filter, setFilter] = useState<'All' | string>('All')
  const [sort, setSort] = useState<SortKey>('hire_fee')

  const specialities = useMemo(() => {
    if (!staff) return []
    return Array.from(new Set(staff.pool.map((t) => t.speciality))).sort()
  }, [staff])

  const visible = useMemo(() => {
    if (!staff) return []
    const list = staff.pool.filter((t) => filter === 'All' || t.speciality === filter)
    return [...list].sort((a, b) => {
      if (sort === 'name') return a.name.localeCompare(b.name)
      if (sort === 'hire_fee') return a.hire_fee - b.hire_fee
      if (sort === 'weekly_salary') return a.weekly_salary - b.weekly_salary
      return b.skills[sort] - a.skills[sort]
    })
  }, [staff, filter, sort])

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
            : 'Hire a trainer from the pool below — you pay a fee now, then a weekly salary.'
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
        <>
          <Card style={{ display: 'flex', flexDirection: 'column', gap: 10, padding: '14px 16px' }}>
            <div style={{ display: 'flex', flexWrap: 'wrap', alignItems: 'center', gap: 8 }}>
              <ChipLabel>SPECIALITY</ChipLabel>
              {['All', ...specialities].map((f) => (
                <Chip key={f} active={filter === f} onClick={() => setFilter(f)}>
                  {f}
                </Chip>
              ))}
            </div>
            <div style={{ display: 'flex', flexWrap: 'wrap', alignItems: 'center', gap: 8 }}>
              <ChipLabel>SORT</ChipLabel>
              {SORT_OPTIONS.map((o) => (
                <Chip key={o.key} active={sort === o.key} onClick={() => setSort(o.key)}>
                  {o.label}
                </Chip>
              ))}
              <span
                style={{
                  marginLeft: 'auto',
                  fontSize: 12,
                  color: color.muted,
                  fontFamily: font.mono,
                }}
              >
                {visible.length} of {staff.pool.length} trainers
              </span>
            </div>
          </Card>

          <div
            style={{
              display: 'grid',
              gridTemplateColumns: 'repeat(auto-fill, minmax(288px, 1fr))',
              gap: 12,
            }}
          >
            {visible.map((trainer) => {
              const affordable = trainer.hire_fee <= staff.balance
              return (
                <TrainerCard
                  key={trainer.id}
                  trainer={trainer}
                  note={
                    affordable
                      ? undefined
                      : "You cannot afford this trainer's fee."
                  }
                  action={
                    <Button
                      onClick={() => handleHire(trainer.id)}
                      disabled={!affordable || pending}
                      style={{ opacity: pending || !affordable ? 0.6 : 1 }}
                    >
                      Hire
                    </Button>
                  }
                />
              )
            })}
          </div>
        </>
      )}
    </PageBody>
  )
}

function TrainerCard({
  trainer,
  action,
  note,
}: {
  trainer: Trainer
  action: React.ReactNode
  note?: string
}) {
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

      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          gap: 10,
          borderTop: `1px solid ${color.dividerStrong}`,
          paddingTop: 10,
        }}
      >
        <span style={{ fontSize: 12, color: color.mutedStrong, fontFamily: font.mono }}>
          Fee {formatMoney(trainer.hire_fee)}
        </span>
        <span style={{ fontSize: 12, color: color.mutedStrong, fontFamily: font.mono }}>
          {formatMoney(trainer.weekly_salary)}/week
        </span>
      </div>

      {note ? (
        <div style={{ fontSize: 12, color: color.negative }}>{note}</div>
      ) : null}
    </Card>
  )
}
