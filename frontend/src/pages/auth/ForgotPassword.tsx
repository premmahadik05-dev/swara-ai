import { useEffect, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import { api } from '../../api/client'
import { AuthLayout, FormAlert, TextField } from '../../components/AuthKit'
import { Button } from '../../components/ui'
import { useAsync } from '../../lib/hooks'
import { EMAIL_RE, errMessage } from './helpers'

export default function ForgotPassword() {
  const cfg = useAsync(() => api.authConfig(), [])
  const [email, setEmail] = useState('')
  const [err, setErr] = useState<string | null>(null)
  const [formErr, setFormErr] = useState<string | null>(null)
  const [sent, setSent] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const ref = useRef<HTMLInputElement>(null)
  useEffect(() => { document.title = 'Reset password · SWARA AI' }, [])

  const submit = async (e: React.FormEvent) => {
    e.preventDefault()
    if (busy) return
    setFormErr(null)
    if (!EMAIL_RE.test(email.trim())) { setErr('Enter the e-mail address you signed up with.'); ref.current?.focus(); return }
    setErr(null)
    setBusy(true)
    try { setSent((await api.forgotPassword(email.trim())).message) } catch (e2) { setFormErr(errMessage(e2)) } finally { setBusy(false) }
  }

  // When the server cannot send e-mail, say so up front instead of showing a form that cannot work.
  if (cfg.data && !cfg.data.email_configured) {
    return (
      <AuthLayout title="Reset your password" foot={<Link to="/sign-in">Back to sign in</Link>}>
        <FormAlert tone="warn">This server is not set up to send e-mail, so a reset link cannot be sent.</FormAlert>
        <div className="auth-steps">
          <p><b>Staff:</b> ask the shop owner to reset your password.</p>
          <p><b>Owner:</b> on the computer that runs SWARA AI, open a terminal in the project folder and run:</p>
          <pre className="auth-code">backend\.venv\Scripts\python.exe scripts\auth_admin.py reset-password --email you@example.com</pre>
          <p className="muted small">To enable reset by e-mail, add the SMTP settings described in docs/AUTHENTICATION.md.</p>
        </div>
      </AuthLayout>
    )
  }

  return (
    <AuthLayout title="Reset your password" lead="Enter your e-mail address and we will send a link to choose a new password." foot={<Link to="/sign-in">Back to sign in</Link>}>
      {sent ? (
        <FormAlert tone="ok">{sent}</FormAlert>
      ) : (
        <>
          {formErr && <FormAlert tone="bad">{formErr}</FormAlert>}
          <form onSubmit={submit} noValidate className="auth-form">
            <TextField ref={ref} label="E-mail address" type="email" name="email" autoComplete="email" inputMode="email" autoCapitalize="off" spellCheck={false}
                       value={email} onChange={(e) => setEmail(e.target.value)} error={err} autoFocus />
            <Button type="submit" size="lg" className="auth-submit" loading={busy}>{busy ? 'Sending…' : 'Send reset link'}</Button>
          </form>
        </>
      )}
    </AuthLayout>
  )
}
