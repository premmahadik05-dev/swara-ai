import { useEffect, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import { api } from '../../api/client'
import { AuthLayout, FormAlert, PasswordField, StrengthMeter } from '../../components/AuthKit'
import { Button } from '../../components/ui'
import { firstProblem } from '../../lib/password'
import { errCode, errMessage } from './helpers'

export default function ResetPassword() {
  // Read the one-time token once, then take it out of the address bar so it is not left in history or sent in a Referer.
  const [token] = useState(() => new URLSearchParams(window.location.search).get('token') ?? '')
  useEffect(() => {
    document.title = 'Choose a new password · SWARA AI'
    if (token) window.history.replaceState(null, '', window.location.pathname)
  }, [token])
  const [password, setPassword] = useState('')
  const [confirm, setConfirm] = useState('')
  const [errors, setErrors] = useState<{ password?: string; confirm?: string }>({})
  const [formErr, setFormErr] = useState<{ code: string; msg: string } | null>(null)
  const [busy, setBusy] = useState(false)
  const [ok, setOk] = useState(false)
  const pRef = useRef<HTMLInputElement>(null)
  const cRef = useRef<HTMLInputElement>(null)

  if (!token && !ok) {
    return (
      <AuthLayout title="This link is not complete" foot={<Link to="/sign-in">Back to sign in</Link>}>
        <FormAlert tone="bad">The reset link is missing its code. Open the link from your e-mail again, or <Link to="/forgot-password">request a new one</Link>.</FormAlert>
      </AuthLayout>
    )
  }
  if (ok) {
    return (
      <AuthLayout title="Password changed">
        <div className="auth-done" role="status">
          <p>Your password has been changed and every device was signed out. Sign in with the new password.</p>
          <div className="auth-actions"><Link className="btn large" to="/sign-in">Go to sign in</Link></div>
        </div>
      </AuthLayout>
    )
  }

  const submit = async (e: React.FormEvent) => {
    e.preventDefault()
    if (busy) return
    const p: typeof errors = {}
    const prob = firstProblem(password)
    if (prob) p.password = prob
    if (confirm !== password) p.confirm = 'The two passwords do not match.'
    setErrors(p); setFormErr(null)
    if (p.password) { pRef.current?.focus(); return }
    if (p.confirm) { cRef.current?.focus(); return }
    setBusy(true)
    try { await api.resetPassword(token, password, confirm); setOk(true) } catch (err) {
      const code = errCode(err)
      if (code === 'WEAK_PASSWORD') { setErrors({ password: errMessage(err) }); pRef.current?.focus() } else setFormErr({ code, msg: errMessage(err) })
    } finally { setBusy(false) }
  }

  return (
    <AuthLayout title="Choose a new password" lead="Use a password you have not used elsewhere." foot={<Link to="/sign-in">Back to sign in</Link>}>
      {formErr && <FormAlert tone="bad">{formErr.msg}{formErr.code === 'INVALID_TOKEN' && <> <Link to="/forgot-password">Request a new link</Link></>}</FormAlert>}
      <form onSubmit={submit} noValidate className="auth-form">
        <PasswordField ref={pRef} label="New password" name="new-password" autoComplete="new-password" value={password} onChange={(e) => setPassword(e.target.value)} error={errors.password} autoFocus />
        <StrengthMeter password={password} />
        <PasswordField ref={cRef} label="Confirm new password" name="confirm-password" autoComplete="new-password" value={confirm} onChange={(e) => setConfirm(e.target.value)} error={errors.confirm} />
        <Button type="submit" size="lg" className="auth-submit" loading={busy}>{busy ? 'Saving…' : 'Change password'}</Button>
      </form>
    </AuthLayout>
  )
}
