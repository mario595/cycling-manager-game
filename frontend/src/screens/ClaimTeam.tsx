import { useState } from 'react'
import type { CSSProperties, ReactNode } from 'react'
import { Navigate } from 'react-router-dom'

import { Button, Card, PageBody, PageHeading } from '../components/primitives'
import { color, font } from '../theme'
import { useAuth } from '../useAuth'

export function ClaimTeam() {
  const { me, loading, claim } = useAuth()
  const [name, setName] = useState('')
  const [code, setCode] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState<string | null>(null)

  if (loading) return null
  if (!me?.authenticated) return <Navigate to="/login" replace />
  if (me.team) return <Navigate to="/" replace />

  const submit = async () => {
    setSubmitting(true)
    setError(null)
    try {
      await claim(name, code)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not claim a team.')
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <PageBody gap={18} paddingTop={26}>
      <PageHeading
        eyebrow="NEW MANAGER"
        title="Claim a team"
        subtitle="Pick a name and a code for the team you're taking over."
        titleSize={29}
      />

      <Card style={{ padding: '20px 22px', maxWidth: 380, display: 'flex', flexDirection: 'column', gap: 14 }}>
        <Field label="Team name">
          <input
            type="text"
            value={name}
            onChange={(e) => setName(e.target.value)}
            style={inputStyle}
          />
        </Field>
        <Field label="Team code (3 letters)">
          <input
            type="text"
            value={code}
            maxLength={3}
            onChange={(e) => setCode(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && void submit()}
            style={inputStyle}
          />
        </Field>

        {error ? <div style={{ fontSize: 12.5, color: color.negative }}>{error}</div> : null}

        <Button
          variant="primary"
          onClick={() => void submit()}
          style={{
            width: '100%',
            opacity: submitting ? 0.6 : 1,
            cursor: submitting ? 'not-allowed' : 'pointer',
          }}
        >
          {submitting ? 'Claiming team…' : 'Claim team'}
        </Button>
      </Card>
    </PageBody>
  )
}

function Field({ label, children }: { label: string; children: ReactNode }) {
  return (
    <label style={{ display: 'flex', flexDirection: 'column', gap: 5 }}>
      <span style={{ fontSize: 10, letterSpacing: '1px', color: color.mutedStrong, fontFamily: font.mono }}>
        {label.toUpperCase()}
      </span>
      {children}
    </label>
  )
}

const inputStyle: CSSProperties = {
  fontSize: 13.5,
  padding: '9px 11px',
  borderRadius: 8,
  border: `1px solid ${color.borderButton}`,
  background: color.surface,
  fontFamily: font.sans,
}
