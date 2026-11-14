import { useEffect, useRef, useState } from 'react'
import { Link, Navigate, useNavigate } from 'react-router-dom'
import { api } from '../../api/client'
import { AuthLayout, FormAlert, PasswordField, StrengthMeter, TextField } from '../../components/AuthKit'
import { Icon } from '../../components/Icons'
import { Button } from '../../components/ui'
import { useAuth } from '../../lib/auth'
import { useAsync } from '../../lib/hooks'
import { firstProblem } from '../../lib/password'
import type { AuthUser } from '../../types'
import { EMAIL_RE, errCode, errMessage, fieldForCode, type FieldName } from './helpers'

export default function SignUp() {
  const auth = useAuth()
  const nav = useNavigate()
  const cfg = useAsync(() => api.authConfig(), [])
  const [name, setName] = useState('')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [confirm, setConfirm] = useState('')
  const [terms, setTerms] = useState(false)
  const [errors, setErrors] = useState<Partial<Record<FieldName, string>>>({})
  const [formErr, setFormErr] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const [done, setDone] = useState<{ user: AuthUser | null; verify: boolean; email: string } | null>(null)
  const refs = { name: useRef<HTMLInputElement>(null), email: useRef<HTMLInputElement>(null), password: useRef<HTMLInputElement>(null), confirm: useRef<HTMLInputElement>(null), terms: useRef<HTMLInputElement>(null) }
  const [resent, setResent] = useState<string | null>(null)

  useEffect(() => { document.title = 'Create account · SWARA AI' }, [])
  // Someone who is already signed in has no reason to be here. Signing up signs the person in a moment before the success
  // screen is set, so a request in flight (busy) or a finished one (done) must not trigger this redirect.
  if (auth.status === 'in' && !done && !busy) return <Navigate to="/dashboard" replace />

  const c = cfg.data

  const validate = () => {
    const p: Partial<Record<FieldName, string>> = {}
    const n = name.trim().replace(/\s+/g, ' ')
    if (n.length < 2 || n.length > 80 || /[<>]/.test(n)) p.name = 'Enter your full name (2 to 80 characters).'
    if (!EMAIL_RE.test(email.trim())) p.email = 'Enter a valid e-mail address.'
    const pw = firstProblem(password, { email, name })
    if (pw) p.password = pw
    if (confirm !== password) p.confirm = 'The two passwords do not match.'
    if (!terms) p.terms = 'Accept the Terms and Privacy Policy to continue.'
    return p
  }

  const submit = async (e: React.FormEvent) => {
    e.preventDefault()
    if (busy) return
    const p = validate()
    setErrors(p)
    setFormErr(null)
    const first = (['name', 'email', 'password', 'confirm', 'terms'] as FieldName[]).find((k) => p[k])
    if (first) { refs[first].current?.focus(); return }
    setBusy(true)
    try {
      const r = await auth.signUp({ full_name: name.trim(), email: email.trim(), password, confirm_password: confirm, accept_terms: terms })
      setDone({ user: r.user, verify: r.verification_required, email: email.trim().toLowerCase() })
    } catch (err) {
      const f = fieldForCode(errCode(err))
      if (f) { setErrors({ [f]: errMessage(err) }); refs[f].current?.focus() } else setFormErr(errMessage(err))
    } finally {
      setBusy(false)
    }
  }

  if (done) {
    return (
      <AuthLayout title={done.verify ? 'Check your inbox' : 'Your account is ready'}>
        <div className="auth-done" role="status">
          <span className="auth-done-icon" aria-hidden><Icon name="check" size={22} /></span>
          {done.verify ? (
            <>
              <p>We sent a confirmation link to <b>{done.email}</b>. Open it to finish creating your account, then sign in. The link works once and expires in 24 hours.</p>
              {resent && <FormAlert tone="ok">{resent}</FormAlert>}
              <div className="auth-actions">
                <Link className="btn large" to="/sign-in">Go to sign in</Link>
                <Button variant="secondary" size="lg" onClick={async () => { try { setResent((await api.resendVerification(done.email)).message) } catch (err) { setResent(errMessage(err)) } }}>Send the link again</Button>
              </div>
            </>
          ) : (
            <>
              <p>Welcome, {done.user?.full_name.split(' ')[0]}. You are signed in{done.user?.role === 'owner' ? ' as the shop owner' : ' as staff'}.</p>
              {done.user?.role === 'owner'
                ? <p className="muted small">As the owner you can change stock and prices, connect Gnani voice, and manage who else can sign in.</p>
                : <p className="muted small">You can take orders and see the shop's numbers. Only the owner can change stock, prices and settings.</p>}
              <div className="auth-actions"><Button size="lg" onClick={() => nav('/dashboard', { replace: true })}>Open the dashboard</Button></div>
            </>
          )}
        </div>
      </AuthLayout>
    )
  }

  if (c && !c.signup_open) {
    return (
      <AuthLayout title="Sign-up is closed" lead="This server is not accepting new accounts." foot={<>Already have an account? <Link to="/sign-in">Sign in</Link></>}>
        <FormAlert tone="info">Ask the shop owner to add you. If you are the owner, set <code>ALLOW_SIGNUP=true</code> in the server settings or use <code>scripts/auth_admin.py</code>.</FormAlert>
      </AuthLayout>
    )
  }

  return (
    <AuthLayout title="Create your account" lead="Start taking orders by voice in a few minutes." foot={<>Already have an account? <Link to="/sign-in">Sign in</Link></>}>
      {c && !c.has_owner && (
        <FormAlert tone="info">
          {c.owner_email_set
            ? <>The owner account on this server is reserved for the e-mail address set by the person who installed it.</>
            : <>You are the first person here, so this account will be the <b>shop owner</b>.</>}
        </FormAlert>
      )}
      {formErr && <FormAlert tone="bad">{formErr}</FormAlert>}
      <form onSubmit={submit} noValidate className="auth-form">
        <TextField ref={refs.name} label="Full name" name="name" autoComplete="name" value={name} onChange={(e) => setName(e.target.value)} error={errors.name} autoFocus />
        <TextField ref={refs.email} label="E-mail address" type="email" name="email" autoComplete="email" inputMode="email" autoCapitalize="off" spellCheck={false}
                   value={email} onChange={(e) => setEmail(e.target.value)} error={errors.email} />
        <PasswordField ref={refs.password} label="Password" name="new-password" autoComplete="new-password" value={password} onChange={(e) => setPassword(e.target.value)} error={errors.password} />
        <StrengthMeter password={password} email={email} name={name} />
        <PasswordField ref={refs.confirm} label="Confirm password" name="confirm-password" autoComplete="new-password" value={confirm} onChange={(e) => setConfirm(e.target.value)} error={errors.confirm} />
        <div className={`afield${errors.terms ? ' invalid' : ''}`}>
          <label className="acheck">
            <input ref={refs.terms} type="checkbox" checked={terms} onChange={(e) => setTerms(e.target.checked)} aria-invalid={errors.terms ? true : undefined} aria-describedby={errors.terms ? 'terms-msg' : undefined} />
            <span>I accept the <Link to="/terms" target="_blank" rel="noopener">Terms</Link> and the <Link to="/privacy" target="_blank" rel="noopener">Privacy Policy</Link></span>
          </label>
          {errors.terms && <span id="terms-msg" className="afield-msg err" role="alert">{errors.terms}</span>}
        </div>
        <Button type="submit" size="lg" className="auth-submit" loading={busy}>{busy ? 'Creating account…' : 'Create account'}</Button>
      </form>
    </AuthLayout>
  )
}
