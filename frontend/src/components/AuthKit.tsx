import { forwardRef, useId, useState, type InputHTMLAttributes, type ReactNode } from 'react'
import { Link } from 'react-router-dom'
import { Icon } from './Icons'
import { Logo } from './Logo'
import { STRENGTH_LABEL, rules, strength } from '../lib/password'

/** Shared pieces of the sign-in, sign-up and recovery screens. */

export function AuthLayout({ title, lead, children, foot }: { title: string; lead?: ReactNode; children: ReactNode; foot?: ReactNode }) {
  return (
    <div className="auth-page">
      <a href="#auth-main" className="skip-link">Skip to form</a>
      <main id="auth-main" className="auth-main" tabIndex={-1}>
        <div className="auth-col">
          <Link to="/" className="auth-logo" aria-label="SWARA AI, home"><Logo height={38} decorative /></Link>
          <h1 className="auth-title">{title}</h1>
          {lead && <p className="auth-lead">{lead}</p>}
          {children}
          {foot && <div className="auth-foot">{foot}</div>}
        </div>
      </main>
      <aside className="auth-aside" aria-label="About SWARA AI">
        <div className="auth-aside-in">
          <p className="auth-aside-tag">Every Voice. Smarter Commerce.</p>
          <p className="auth-aside-body">Say the order in Gujarati, Hindi, English, a mix, or one of seven more Indian languages. SWARA AI builds the bill, checks the shelf and keeps your sales numbers.</p>
          <ul className="auth-points">
            <li><Icon name="mic" size={18} /><span>Voice ordering in the languages your customers speak</span></li>
            <li><Icon name="box" size={18} /><span>Stock checked before every order is confirmed</span></li>
            <li><Icon name="chart" size={18} /><span>Sales and best sellers computed from your own orders</span></li>
          </ul>
        </div>
      </aside>
    </div>
  )
}

interface FieldProps extends Omit<InputHTMLAttributes<HTMLInputElement>, 'id'> {
  label: string
  error?: string | null
  hint?: ReactNode
  /** extra element on the label line, e.g. "Forgot password?" */
  aside?: ReactNode
  id?: string
}

export const TextField = forwardRef<HTMLInputElement, FieldProps>(function TextField({ label, error, hint, aside, id, ...rest }, ref) {
  const auto = useId()
  const fid = id ?? auto
  const mid = `${fid}-msg`
  return (
    <div className={`afield${error ? ' invalid' : ''}`}>
      <div className="afield-top"><label htmlFor={fid}>{label}</label>{aside}</div>
      <input ref={ref} id={fid} aria-invalid={error ? true : undefined} aria-describedby={error || hint ? mid : undefined} {...rest} />
      {error ? <span id={mid} className="afield-msg err" role="alert">{error}</span> : hint ? <span id={mid} className="afield-msg">{hint}</span> : null}
    </div>
  )
})

export const PasswordField = forwardRef<HTMLInputElement, Omit<FieldProps, 'type'>>(function PasswordField({ label, error, hint, aside, id, ...rest }, ref) {
  const auto = useId()
  const fid = id ?? auto
  const mid = `${fid}-msg`
  const [show, setShow] = useState(false)
  return (
    <div className={`afield${error ? ' invalid' : ''}`}>
      <div className="afield-top"><label htmlFor={fid}>{label}</label>{aside}</div>
      <div className="afield-pw">
        <input ref={ref} id={fid} type={show ? 'text' : 'password'} aria-invalid={error ? true : undefined} aria-describedby={error || hint ? mid : undefined}
               spellCheck={false} autoCapitalize="off" {...rest} />
        <button type="button" className="afield-eye" onClick={() => setShow((s) => !s)} aria-pressed={show} aria-label={show ? `Hide ${label.toLowerCase()}` : `Show ${label.toLowerCase()}`}>
          {show ? 'Hide' : 'Show'}
        </button>
      </div>
      {error ? <span id={mid} className="afield-msg err" role="alert">{error}</span> : hint ? <span id={mid} className="afield-msg">{hint}</span> : null}
    </div>
  )
})

export function StrengthMeter({ password, email, name }: { password: string; email?: string; name?: string }) {
  const s = strength(password)
  const list = rules(password, { email, name })
  return (
    <div className="meter" aria-live="polite">
      <div className={`meter-bar lvl-${s}`} role="img" aria-label={password ? `Password strength: ${STRENGTH_LABEL[s]}` : 'Password strength: not entered'}>
        {[1, 2, 3, 4].map((i) => <i key={i} className={i <= s ? 'on' : ''} />)}
      </div>
      <p className="meter-label">{password ? STRENGTH_LABEL[s] : 'Choose a password'}</p>
      <ul className="meter-rules">
        {list.map((r) => <li key={r.id} className={password && r.ok ? 'ok' : ''}><Icon name={password && r.ok ? 'check' : 'minus'} size={13} /><span>{r.label}</span></li>)}
      </ul>
    </div>
  )
}

export function FormAlert({ tone = 'bad', children }: { tone?: 'bad' | 'ok' | 'info' | 'warn'; children: ReactNode }) {
  return <div className={`auth-alert ${tone}`} role={tone === 'bad' ? 'alert' : 'status'}><Icon name={tone === 'ok' ? 'check' : tone === 'info' ? 'info' : 'alert'} size={16} /><div>{children}</div></div>
}
