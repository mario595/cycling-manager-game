import { useState } from 'react'
import type { CSSProperties, ReactNode } from 'react'
import { Link, Navigate } from 'react-router-dom'

import { Button, Card, PageBody, PageHeading } from '../components/primitives'
import { color, font } from '../theme'
import { useAuth } from '../useAuth'

export function Register() {
  const { me, loading, register } = useAuth()
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [displayName, setDisplayName] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState<string | null>(null)

  if (loading) return null
  if (me?.authenticated) return <Navigate to="/" replace />

  const submit = async () => {
    setSubmitting(true)
    setError(null)
    try {
      await register(email, password, displayName)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not register.')
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <PageBody gap={18} paddingTop={26}>
      <PageHeading eyebrow="NEW MANAGER" title="Register" subtitle="Create your account." titleSize={29} />

      <Card style={{ padding: '20px 22px', maxWidth: 380, display: 'flex', flexDirection: 'column', gap: 14 }}>
        <Field label="Display name">
          <input
            type="text"
            value={displayName}
            onChange={(e) => setDisplayName(e.target.value)}
            style={inputStyle}
          />
        </Field>
        <Field label="Email">
          <input
            type="email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            style={inputStyle}
          />
        </Field>
        <Field label="Password">
          <input
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
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
          {submitting ? 'Creating account…' : 'Create account'}
        </Button>

        <div style={{ fontSize: 12.5, color: color.muted }}>
          Already have an account? <Link to="/login" style={{ color: color.accentInk }}>Log in</Link>
        </div>
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
