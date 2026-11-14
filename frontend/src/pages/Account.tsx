import { useEffect, useRef, useState } from 'react'
import { api } from '../api/client'
import { FormAlert, PasswordField, StrengthMeter, TextField } from '../components/AuthKit'
import { useToast } from '../components/Toast'
import { Avatar, Badge, Button, Card, Empty, ErrorNote, Field, Note, PageHeader, SkeletonRows } from '../components/ui'
import { useAuth, useSignOut } from '../lib/auth'
import { istTime } from '../lib/format'
import { LANG_META } from '../lib/languages'
import { useAsync } from '../lib/hooks'
import { firstProblem } from '../lib/password'
import { errCode, errMessage } from './auth/helpers'

export default function Account() {
  const { user } = useAuth()
  const signOut = useSignOut()
  if (!user) return null
  const owner = user.role === 'owner'
  const leave = () => { void signOut() }
  return (
    <>
      <PageHeader title="Account" description="Your details, password and the devices that are signed in."
        meta={<Badge tone={owner ? 'accent' : 'plain'}>{owner ? 'Shop owner' : 'Staff'}</Badge>}
        actions={<Button variant="secondary" icon="logout" onClick={leave}>Sign out</Button>} />
      <div className="stack">
        <div className="cols two">
          <ProfileCard />
          <PasswordCard />
        </div>
        <SessionsCard />
        {owner && <TeamCard />}
        {owner && <MessagesCard />}
      </div>
    </>
  )
}

function ProfileCard() {
  const { user, setUser } = useAuth()
  const { toast } = useToast()
  const [name, setName] = useState(user?.full_name ?? '')
  const [lang, setLang] = useState(user?.preferences.language ?? '')
  const [err, setErr] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  if (!user) return null
  const dirty = name.trim().replace(/\s+/g, ' ') !== user.full_name || (lang || '') !== (user.preferences.language ?? '')

  const save = async (e: React.FormEvent) => {
    e.preventDefault()
    setErr(null)
    const body: { full_name?: string; language?: string } = {}
    if (name.trim().replace(/\s+/g, ' ') !== user.full_name) body.full_name = name
    if (lang && lang !== (user.preferences.language ?? '')) body.language = lang
    if (!Object.keys(body).length) return
    setBusy(true)
    try { const r = await api.updateProfile(body); setUser(r.user); setName(r.user.full_name); toast('Profile saved.', 'ok') } catch (x) { setErr(errMessage(x)) } finally { setBusy(false) }
  }

  return (
    <Card title="Profile" description="How you appear in the app">
      <div className="row" style={{ marginBottom: 14 }}>
        <Avatar name={user.full_name} size="lg" />
        <div>
          <div style={{ fontWeight: 600 }}>{user.full_name}</div>
          <div className="muted small">{user.email} {user.email_verified ? <Badge tone="ok">Confirmed</Badge> : <Badge tone="plain" title="This server did not check that this address is yours. It only does that when e-mail sending is set up.">Not checked</Badge>}</div>
        </div>
      </div>
      {err && <FormAlert tone="bad">{err}</FormAlert>}
      <form className="auth-form" onSubmit={save} noValidate>
        <TextField label="Full name" name="name" autoComplete="name" value={name} onChange={(e) => setName(e.target.value)} />
        <Field label="Order desk language" htmlFor="pref-lang" hint="The language the Order desk starts in on every device.">
          <select id="pref-lang" value={lang} onChange={(e) => setLang(e.target.value as typeof lang)}>
            <option value="">Gujarati (default)</option>
            {LANG_META.map((l) => <option key={l.key} value={l.key}>{l.name}</option>)}
          </select>
        </Field>
        <p className="muted small" style={{ margin: 0 }}>
          Member since {user.created_at ? istTime(user.created_at) : '-'}. Last sign-in {user.last_login_at ? istTime(user.last_login_at) : 'this one'}. Your e-mail address is your sign-in name and cannot be changed here.
        </p>
        <div className="row"><Button type="submit" disabled={!dirty} loading={busy}>Save changes</Button></div>
      </form>
    </Card>
  )
}

function PasswordCard() {
  const { user } = useAuth()
  const { toast } = useToast()
  const [cur, setCur] = useState('')
  const [pw, setPw] = useState('')
  const [conf, setConf] = useState('')
  const [errs, setErrs] = useState<{ cur?: string; pw?: string; conf?: string }>({})
  const [formErr, setFormErr] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const curRef = useRef<HTMLInputElement>(null)
  const pwRef = useRef<HTMLInputElement>(null)
  const confRef = useRef<HTMLInputElement>(null)

  const submit = async (e: React.FormEvent) => {
    e.preventDefault()
    const p: typeof errs = {}
    if (!cur) p.cur = 'Enter your current password.'
    const prob = firstProblem(pw, { email: user?.email, name: user?.full_name })
    if (prob) p.pw = prob
    if (conf !== pw) p.conf = 'The two passwords do not match.'
    setErrs(p); setFormErr(null)
    if (p.cur) { curRef.current?.focus(); return }
    if (p.pw) { pwRef.current?.focus(); return }
    if (p.conf) { confRef.current?.focus(); return }
    setBusy(true)
    try {
      const r = await api.changePassword(cur, pw)
      setCur(''); setPw(''); setConf('')
      toast(r.other_sessions_signed_out ? `Password changed. ${r.other_sessions_signed_out} other device(s) were signed out.` : 'Password changed.', 'ok')
    } catch (x) {
      const c = errCode(x)
      if (c === 'WRONG_PASSWORD') { setErrs({ cur: errMessage(x) }); curRef.current?.focus() }
      else if (c === 'WEAK_PASSWORD' || c === 'SAME_PASSWORD') { setErrs({ pw: errMessage(x) }); pwRef.current?.focus() }
      else setFormErr(errMessage(x))
    } finally { setBusy(false) }
  }

  return (
    <Card title="Password" description="Changing it signs out every other device">
      {formErr && <FormAlert tone="bad">{formErr}</FormAlert>}
      <form className="auth-form" onSubmit={submit} noValidate>
        <PasswordField ref={curRef} label="Current password" name="current-password" autoComplete="current-password" value={cur} onChange={(e) => setCur(e.target.value)} error={errs.cur} />
        <PasswordField ref={pwRef} label="New password" name="new-password" autoComplete="new-password" value={pw} onChange={(e) => setPw(e.target.value)} error={errs.pw} />
        <StrengthMeter password={pw} email={user?.email} name={user?.full_name} />
        <PasswordField ref={confRef} label="Confirm new password" name="confirm-password" autoComplete="new-password" value={conf} onChange={(e) => setConf(e.target.value)} error={errs.conf} />
        <div className="row"><Button type="submit" loading={busy}>Change password</Button></div>
      </form>
    </Card>
  )
}

function SessionsCard() {
  const { toast } = useToast()
  const signOut = useSignOut()
  const s = useAsync(() => api.deviceSessions(), [])
  const [busy, setBusy] = useState<string | null>(null)
  useEffect(() => { s.reload() }, []) // eslint-disable-line react-hooks/exhaustive-deps

  const revoke = async (id: string, current: boolean) => {
    setBusy(id)
    try {
      await api.revokeDeviceSession(id)
      if (current) { await signOut(); return }
      toast('That device was signed out.', 'ok'); s.reload()
    } catch (x) { toast(errMessage(x), 'bad') } finally { setBusy(null) }
  }
  const others = s.data?.filter((x) => !x.current).length ?? 0
  const revokeOthers = async () => {
    setBusy('others')
    try { const r = await api.revokeOtherSessions(); toast(`${r.signed_out} device(s) signed out.`, 'ok'); s.reload() } catch (x) { toast(errMessage(x), 'bad') } finally { setBusy(null) }
  }

  return (
    <Card title="Signed-in devices" description="Browsers where your account is currently signed in"
      actions={others > 0 ? <Button variant="secondary" size="sm" onClick={revokeOthers} loading={busy === 'others'}>Sign out all other devices</Button> : undefined} flush>
      <ErrorNote error={s.error} onRetry={s.reload} />
      {s.loading && !s.data ? <SkeletonRows rows={2} cols={3} /> : s.data && (
        <div className="table-wrap">
          <table className="tbl compact">
            <thead><tr><th>Device</th><th>Signed in</th><th>Last active</th><th>Ends</th><th><span className="sr">Action</span></th></tr></thead>
            <tbody>
              {s.data.map((d) => (
                <tr key={d.id}>
                  <td>{d.device} {d.current && <Badge tone="ok">This device</Badge>}{d.remember && <span className="sub">Kept signed in</span>}</td>
                  <td className="muted nowrap">{istTime(d.created_at)}</td>
                  <td className="muted nowrap">{istTime(d.last_seen_at)}</td>
                  <td className="muted nowrap">{istTime(d.expires_at)}</td>
                  <td className="num"><Button size="sm" variant="secondary" onClick={() => revoke(d.id, d.current)} loading={busy === d.id} aria-label={d.current ? 'Sign out of this device' : `Sign out ${d.device}`}>Sign out</Button></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </Card>
  )
}

function TeamCard() {
  const { toast } = useToast()
  const { user } = useAuth()
  const t = useAsync(() => api.team(), [])
  const [busy, setBusy] = useState<number | null>(null)
  const toggle = async (id: number, active: boolean) => {
    setBusy(id)
    try { await api.setUserActive(id, active); toast(active ? 'Account turned on.' : 'Account turned off and signed out.', 'ok'); t.reload() } catch (x) { toast(errMessage(x), 'bad') } finally { setBusy(null) }
  }
  return (
    <Card title="Team" description="Everyone who can sign in to this shop. Staff can take orders and read the numbers; only you can change stock, prices and settings." flush>
      <ErrorNote error={t.error} onRetry={t.reload} />
      {t.loading && !t.data ? <SkeletonRows rows={3} cols={4} /> : t.data && (
        <div className="table-wrap">
          <table className="tbl compact">
            <thead><tr><th>Person</th><th>Role</th><th>Last sign-in</th><th>Status</th><th><span className="sr">Action</span></th></tr></thead>
            <tbody>
              {t.data.map((u) => (
                <tr key={u.id}>
                  <td><b style={{ fontWeight: 550 }}>{u.full_name}</b><span className="sub">{u.email}</span></td>
                  <td>{u.role === 'owner' ? 'Owner' : 'Staff'}</td>
                  <td className="muted nowrap">{u.last_login_at ? istTime(u.last_login_at) : 'Never'}</td>
                  <td><Badge tone={u.is_active ? 'ok' : 'bad'}>{u.is_active ? 'On' : 'Off'}</Badge></td>
                  <td className="num">
                    {u.role !== 'owner' && u.id !== user?.id && (
                      <Button size="sm" variant={u.is_active ? 'danger' : 'secondary'} loading={busy === u.id} onClick={() => toggle(u.id, !u.is_active)} aria-label={`${u.is_active ? 'Turn off' : 'Turn on'} ${u.full_name}`}>{u.is_active ? 'Turn off' : 'Turn on'}</Button>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </Card>
  )
}

function MessagesCard() {
  const { toast } = useToast()
  const m = useAsync(() => api.contactMessages(), [])
  const done = async (id: number) => { try { await api.markMessageHandled(id); m.reload() } catch (x) { toast(errMessage(x), 'bad') } }
  const open = m.data?.filter((x) => !x.handled).length ?? 0
  return (
    <Card title="Messages from the contact form" description={m.data ? `${open} waiting for a reply` : undefined}>
      <ErrorNote error={m.error} onRetry={m.reload} />
      {m.loading && !m.data ? <SkeletonRows rows={2} cols={2} /> : m.data && m.data.length === 0 ? (
        <Empty title="No messages yet" icon="chat">Messages sent from the landing page contact form are kept here.</Empty>
      ) : m.data && (
        <ul className="list-rows msgs">
          {m.data.map((x) => (
            <li key={x.id} className={x.handled ? 'handled' : ''}>
              <div className="grow">
                <div><b style={{ fontWeight: 550 }}>{x.name}</b> <a href={`mailto:${x.email}`}>{x.email}</a> <Badge tone="plain">{x.topic}</Badge> <span className="faint small">{istTime(x.created_at)}</span></div>
                <p className="msg-body">{x.message}</p>
              </div>
              {!x.handled ? <Button size="sm" variant="secondary" onClick={() => done(x.id)}>Mark as handled</Button> : <Badge tone="ok">Handled</Badge>}
            </li>
          ))}
        </ul>
      )}
      <Note>Replies are sent from your own mail app; SWARA AI does not reply on your behalf.</Note>
    </Card>
  )
}
