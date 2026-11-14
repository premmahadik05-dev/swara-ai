import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { api } from '../api/client'
import { Badge, Button, Card, ErrorNote, Field, Note, PageHeader, SkeletonCard } from '../components/ui'
import { LanguagesCard } from '../components/LanguagesCard'
import { PaymentsSettingsCard } from '../components/payments/PaymentsSettingsCard'
import { useToast } from '../components/Toast'
import { ms } from '../lib/format'
import { useAuth } from '../lib/auth'
import { useAsync } from '../lib/hooks'
import { SHOP_RENAMED, cleanShopName, shopNameProblem } from '../lib/shop'

type TestResult = Awaited<ReturnType<typeof api.testGnani>>

/** The shop's name: shown in the sidebar and on printed bills. Owner only. */
function ShopCard({ current, onSaved }: { current: string; onSaved: () => void }) {
  const { toast } = useToast()
  const [name, setName] = useState(current)
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState<string | null>(null)
  useEffect(() => { setName(current) }, [current])
  const clean = cleanShopName(name)
  const problem = shopNameProblem(name)
  const save = async (e: React.FormEvent) => {
    e.preventDefault()
    if (problem || clean === current) return
    setBusy(true); setErr(null)
    try {
      await api.putSettings({ store_name: clean })
      window.dispatchEvent(new Event(SHOP_RENAMED))
      toast('Shop name saved.', 'ok')
      onSaved()
    } catch (e2) { setErr((e2 as Error).message) } finally { setBusy(false) }
  }
  return (
    <Card title="Your shop" description="Shown in the sidebar and at the top of printed bills.">
      <form className="row end" onSubmit={save} aria-label="Rename your shop" style={{ alignItems: 'flex-end' }}>
        <div style={{ flex: '1 1 280px' }}>
          <Field label="Shop name" htmlFor="shop-name" error={err ?? (name !== current ? problem : null)}>
            <input id="shop-name" type="text" value={name} maxLength={80} autoComplete="organization" onChange={(e) => { setName(e.target.value); setErr(null) }} aria-invalid={!!(err || (name !== current && problem))} />
          </Field>
        </div>
        <Button type="submit" loading={busy} disabled={!!problem || clean === current}>Save name</Button>
      </form>
    </Card>
  )
}

export default function Settings() {
  const { toast } = useToast()
  const owner = useAuth().user?.role === 'owner'
  const s = useAsync(() => api.settings(), [])
  const [key, setKey] = useState('')
  const [busy, setBusy] = useState(false)
  const [test, setTest] = useState<TestResult | null>(null)
  const [testErr, setTestErr] = useState<Error | null>(null)
  const g = s.data?.gnani

  const saveKey = async (e: React.FormEvent) => {
    e.preventDefault()
    setBusy(true)
    try { await api.putKey(key.trim()); setKey(''); toast('Key saved on the server. It is never shown again.', 'ok'); s.reload() } catch (err) { toast((err as Error).message, 'bad') } finally { setBusy(false) }
  }
  const patch = async (body: Record<string, unknown>) => {
    try { await api.putSettings(body); toast('Saved.', 'ok'); s.reload() } catch (err) { toast((err as Error).message, 'bad') }
  }
  const runTest = async () => {
    setBusy(true); setTest(null); setTestErr(null)
    try { setTest(await api.testGnani()) } catch (err) { setTestErr(err as Error) } finally { setBusy(false) }
  }

  return (
    <>
      <PageHeader title="Settings" description="Name your shop, connect Gnani, choose the voices used for spoken replies and set up payments." />
      <div className="stack">
        <ErrorNote error={s.error} onRetry={s.reload} />
        {s.loading && !s.data && <div className="cols two"><div className="card card-pad"><SkeletonCard lines={5} height={220} /></div><div className="card card-pad"><SkeletonCard lines={5} height={220} /></div></div>}
        {s.data && g && (
          <>
            {!owner && (
              <Note tone="info"><b>You are signed in as staff.</b> Only the shop owner can change the shop name, the Gnani connection and the voices.</Note>
            )}
            {owner && <ShopCard current={s.data.store_name} onSaved={s.reload} />}
            {owner && <LanguagesCard settings={s.data} onChanged={s.reload} />}
            {owner && <PaymentsSettingsCard settings={s.data} onSaved={s.reload} />}
            {owner ? <div className="cols two">
              <Card title="Gnani connection" description="One key powers both speech models. It stays on the server.">
                <div className="row" style={{ marginBottom: 12 }}>
                  <Badge tone={g.configured ? 'ok' : 'warn'} dot>{g.configured ? `Key set ${g.key_hint ?? ''}` : 'No key yet'}</Badge>
                  <span className="muted small">{g.calls_last_hour} of {g.max_calls_per_hour} calls used this hour</span>
                </div>
                <form className="stack sm" onSubmit={saveKey}>
                  <Field label={g.configured ? 'Replace the API key' : 'Paste your Gnani API key'} htmlFor="gkey">
                    <input id="gkey" type="password" autoComplete="off" spellCheck={false} value={key} onChange={(e) => setKey(e.target.value)} placeholder="Write-only: the server never sends it back" />
                  </Field>
                  <div className="row">
                    <Button type="submit" disabled={busy || key.trim().length < 8}>Save key</Button>
                    <Button variant="secondary" onClick={runTest} disabled={busy || !g.configured} loading={busy && g.configured && key.trim().length < 8 && !test}>Test connection (2 calls)</Button>
                  </div>
                </form>
                <p className="muted small" style={{ marginTop: 12 }}>The key is stored in the server's .env file and used only by the backend. Your browser never receives it.</p>
                {testErr && <div style={{ marginTop: 12 }}><ErrorNote error={testErr} /></div>}
                {test && (
                  <div className="stack sm" style={{ marginTop: 12 }} role="status">
                    <Note tone={test.tts.ok ? 'ok' : 'bad'}><b>Timbre text-to-speech:</b> {test.tts.ok ? `worked in ${ms(test.tts.latency_ms)} (${test.tts.voice}, ${test.tts.bytes} bytes)` : test.tts.error}</Note>
                    <Note tone={test.stt.ok ? 'ok' : test.tts.ok ? 'bad' : 'info'}><b>Prisma speech-to-text:</b> {test.stt.ok ? `heard "${test.stt.transcript}" in ${ms(test.stt.latency_ms)}` : test.tts.ok ? test.stt.error : 'skipped'}</Note>
                    <p className="muted small" style={{ margin: 0 }}>Spoken: "{test.phrase}". A real round trip through both models using your key.</p>
                  </div>
                )}
              </Card>

              <Card title="Speech models" description="What listens and what speaks">
                <div className="stack sm">
                  <Field label="Speech-to-text model" htmlFor="sm">
                    <select id="sm" value={g.stt_model} onChange={(e) => patch({ gnani_stt_model: e.target.value })}>
                      <option value="prisma-v2.5">Prisma v2.5 (default, one language per request)</option>
                      <option value="prisma-v3.0">Prisma v3.0 (auto language, code-mix)</option>
                    </select>
                  </Field>
                  <Field label="Transcript style" htmlFor="sf">
                    <select id="sf" value={g.stt_format} onChange={(e) => patch({ gnani_stt_format: e.target.value })}>
                      <option value="verbatim">Verbatim: words as spoken</option>
                      <option value="transcribe">Transcribe: numbers as digits (Hindi and English, v2.5)</option>
                    </select>
                  </Field>
                  <label className="row check"><input type="checkbox" checked={g.stt_bias} onChange={(e) => patch({ gnani_stt_bias: e.target.checked })} disabled={g.stt_model !== 'prisma-v2.5'} /> Send shop item names to Prisma as hints (v2.5, experimental)</label>
                  <p className="muted small" style={{ margin: 0 }}>Voices, languages and speaking speed are set in the Languages and voices card below.</p>
                  <p className="muted small" style={{ margin: 0 }}>To see how long each spoken order took, open <Link to="/diagnostics">Voice diagnostics</Link>.</p>
                </div>
              </Card>
            </div> : (
              <Card title="Voice connection" description="Set by the shop owner">
                <Badge tone={g.configured ? 'ok' : 'warn'} dot>{g.configured ? 'Voice is connected' : 'Typing only: no Gnani key yet'}</Badge>
              </Card>
            )}

            <div className="cols even">
              <Card title="About Evon v3.3">
                <Note>{s.data.evon.note}</Note>
                <p className="muted small" style={{ margin: '10px 0 0' }}>Status here: {s.data.evon.configured ? 'a self-hosted endpoint is configured' : 'not configured'}. Nothing on this site claims Evon output.</p>
              </Card>
              <Card title="Limits" description="Per message and per device">
                <p className="muted small" style={{ margin: 0 }}>Audio up to {s.data.limits.max_audio_seconds}s and {s.data.limits.max_upload_mb} MB per message. {s.data.limits.rate_limit_per_minute} requests per minute per device.{g.base_url ? ` Gnani base URL: ${g.base_url}.` : ''}</p>
              </Card>
            </div>
          </>
        )}
      </div>
    </>
  )
}
