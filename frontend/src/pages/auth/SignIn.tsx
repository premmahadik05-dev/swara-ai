import { useEffect, useRef, useState } from 'react'
import { Link, Navigate, useLocation, useSearchParams } from 'react-router-dom'
import { api } from '../../api/client'
import { AuthLayout, FormAlert, PasswordField, TextField } from '../../components/AuthKit'
import { Button } from '../../components/ui'
import { safeNext, useAuth } from '../../lib/auth'
import { useAsync } from '../../lib/hooks'
import { EMAIL_RE, errCode, errMessage } from './helpers'

export default function SignIn() {
  const auth = useAuth()
  const [params] = useSearchParams()
  const loc = useLocation()
  const next = safeNext(params.get('next'))
  const cfg = useAsync(() => api.authConfig(), [])
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [remember, setRemember] = useState(false)
  const [errors, setErrors] = useState<{ email?: string; password?: string }>({})
  const [formErr, setFormErr] = useState<{ code: string; msg: string } | null>(null)
  const [busy, setBusy] = useState(false)
  const [resent, setResent] = useState<string | null>(null)
  const emailRef = useRef<HTMLInputElement>(null)
  const passRef = useRef<HTMLInputElement>(null)
  const expired = (loc.state as { expired?: boolean } | null)?.expired === true

  useEffect(() => { document.title = 'Sign in · SWARA AI' }, [])

  if (auth.status === 'in') return <Navigate to={next} replace />

  const submit = async (e: React.FormEvent) => {
    e.preventDefault()
    if (busy) return
    const problems: typeof errors = {}
    if (!EMAIL_RE.test(email.trim())) problems.email = 'Enter the e-mail address you signed up with.'
    if (!password) problems.password = 'Enter your password.'
    setErrors(problems)
    setFormErr(null)
    setResent(null)
    if (problems.email) { emailRef.current?.focus(); return }
    if (problems.password) { passRef.current?.focus(); return }
    setBusy(true)
    try {
      await auth.signIn(email.trim(), password, remember)
    } catch (err) {
      setFormErr({ code: errCode(err), msg: errMessage(err) })
      setPassword('')
      passRef.current?.focus()
    } finally {
      setBusy(false)
    }
  }

  const resend = async () => {
    try { setResent((await api.resendVerification(email.trim())).message) } catch (err) { setResent(errMessage(err)) }
  }

  const c = cfg.data
  return (
    <AuthLayout title="Sign in" lead="Welcome back. Sign in to take orders and see how the shop is doing."
      foot={c && !c.signup_open ? <>New here? Sign-up is closed on this server. Ask the shop owner to add you.</> : <>New to SWARA AI? <Link to="/sign-up">Create an account</Link></>}>
      {auth.bootError && <FormAlert tone="bad">{auth.bootError}</FormAlert>}
      {expired && !formErr && <FormAlert tone="info">Your session has ended, so you were signed out. Sign in again to continue.</FormAlert>}
      {formErr && (
        <FormAlert tone="bad">
          {formErr.msg}
          {formErr.code === 'EMAIL_NOT_VERIFIED' && <> <button type="button" className="linkish" onClick={resend}>Send the link again</button></>}
        </FormAlert>
      )}
      {resent && <FormAlert tone="ok">{resent}</FormAlert>}
      <form onSubmit={submit} noValidate className="auth-form">
        <TextField ref={emailRef} label="E-mail address" type="email" name="email" autoComplete="username" inputMode="email" autoCapitalize="off" spellCheck={false}
                   value={email} onChange={(e) => setEmail(e.target.value)} error={errors.email} autoFocus />
        <PasswordField ref={passRef} label="Password" name="password" autoComplete="current-password" value={password} onChange={(e) => setPassword(e.target.value)} error={errors.password}
                       aside={<Link to="/forgot-password" className="afield-aside">Forgot password?</Link>} />
        <label className="acheck"><input type="checkbox" checked={remember} onChange={(e) => setRemember(e.target.checked)} />
          <span>Keep me signed in on this device{c ? ` for ${c.session.remember_days} days` : ''}</span></label>
        <Button type="submit" size="lg" className="auth-submit" loading={busy}>{busy ? 'Signing in…' : 'Sign in'}</Button>
      </form>
    </AuthLayout>
  )
}
