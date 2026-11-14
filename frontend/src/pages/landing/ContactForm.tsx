import { useId, useRef, useState } from 'react'
import { api } from '../../api/client'
import { FormAlert, TextField } from '../../components/AuthKit'
import { Button } from '../../components/ui'
import { EMAIL_RE, errCode, errMessage } from '../auth/helpers'

const TOPICS = [['general', 'General question'], ['demo', 'See a demo'], ['support', 'Help with my installation'], ['partnership', 'Working together']] as const
type Errs = Partial<Record<'name' | 'email' | 'message', string>>

/** Posts to /api/contact. The server saves the message for the owner and forwards it by e-mail only if SMTP is configured; it says which. */
export function ContactForm() {
  const [name, setName] = useState('')
  const [email, setEmail] = useState('')
  const [topic, setTopic] = useState<(typeof TOPICS)[number][0]>('general')
  const [message, setMessage] = useState('')
  const [website, setWebsite] = useState('')       // honeypot: hidden from people, filled in by bots
  const [errs, setErrs] = useState<Errs>({})
  const [formErr, setFormErr] = useState<string | null>(null)
  const [done, setDone] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const refs = { name: useRef<HTMLInputElement>(null), email: useRef<HTMLInputElement>(null), message: useRef<HTMLTextAreaElement>(null) }
  const uid = useId()

  const submit = async (e: React.FormEvent) => {
    e.preventDefault()
    if (busy) return
    const p: Errs = {}
    const n = name.trim().replace(/\s+/g, ' ')
    if (n.length < 2 || n.length > 80) p.name = 'Enter your name (2 to 80 characters).'
    if (!EMAIL_RE.test(email.trim())) p.email = 'Enter a valid e-mail address so we can reply.'
    const m = message.trim()
    if (m.length < 10) p.message = 'Write at least 10 characters.'
    else if (m.length > 2000) p.message = 'Keep it under 2,000 characters.'
    setErrs(p); setFormErr(null)
    const first = (['name', 'email', 'message'] as const).find((k) => p[k])
    if (first) { refs[first].current?.focus(); return }
    setBusy(true)
    try {
      const r = await api.contact({ name: n, email: email.trim(), topic, message: m, website })
      setDone(r.message)
      setName(''); setEmail(''); setMessage(''); setTopic('general')
    } catch (x) {
      if (errCode(x) === 'BAD_EMAIL') { setErrs({ email: errMessage(x) }); refs.email.current?.focus() } else setFormErr(errMessage(x))
    } finally { setBusy(false) }
  }

  return (
    <form className="auth-form lp-form" onSubmit={submit} noValidate aria-label="Contact form">
      {done && <FormAlert tone="ok">{done}</FormAlert>}
      {formErr && <FormAlert tone="bad">{formErr}</FormAlert>}
      <TextField ref={refs.name} label="Your name" name="name" autoComplete="name" value={name} onChange={(e) => setName(e.target.value)} error={errs.name} />
      <TextField ref={refs.email} label="E-mail address" type="email" name="email" autoComplete="email" inputMode="email" autoCapitalize="off" spellCheck={false}
                 value={email} onChange={(e) => setEmail(e.target.value)} error={errs.email} />
      <div className="afield">
        <div className="afield-top"><label htmlFor={`${uid}-topic`}>What is it about?</label></div>
        <select id={`${uid}-topic`} name="topic" value={topic} onChange={(e) => setTopic(e.target.value as typeof topic)}>
          {TOPICS.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
        </select>
      </div>
      <div className={`afield${errs.message ? ' invalid' : ''}`}>
        <div className="afield-top"><label htmlFor={`${uid}-msg`}>Message</label><span className="afield-aside faint small" aria-hidden>{message.trim().length}/2000</span></div>
        <textarea ref={refs.message} id={`${uid}-msg`} name="message" rows={5} maxLength={2000} value={message} onChange={(e) => setMessage(e.target.value)}
                  aria-invalid={errs.message ? true : undefined} aria-describedby={errs.message ? `${uid}-msg-err` : undefined} />
        {errs.message && <span id={`${uid}-msg-err`} className="afield-msg err" role="alert">{errs.message}</span>}
      </div>
      <div className="lp-hp" aria-hidden="true">
        <label>Leave this empty<input type="text" name="website" tabIndex={-1} autoComplete="off" value={website} onChange={(e) => setWebsite(e.target.value)} /></label>
      </div>
      <Button type="submit" size="lg" loading={busy} className="auth-submit">{busy ? 'Sending…' : 'Send message'}</Button>
      <p className="muted small" style={{ margin: 0 }}>Messages are saved on this server for the shop owner to read. They are also sent by e-mail only if the server has e-mail set up. No reply time is promised.</p>
    </form>
  )
}
