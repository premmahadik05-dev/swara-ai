import { useState } from 'react'
import { api } from '../api/client'
import type { Lang, PublicSettings } from '../types'
import { ms } from '../lib/format'
import { htmlLang, liveSummary } from '../lib/languages'
import { useLanguages, type LangOption } from '../lib/useLanguages'
import { Badge, Button, Card, ErrorNote, Note, SkeletonCard } from './ui'
import { useToast } from './Toast'

type TestResult = Awaited<ReturnType<typeof api.testGnani>>
const LIVE_TONE = { verified: 'ok', partial: 'info', failed: 'bad', simulated: 'warn', none: 'plain' } as const

/**
 * Owner-only: which languages are offered, which Timbre voice speaks each one, and a one-language connection test.
 * The test is a loopback (Timbre speaks the sample sentence, Prisma transcribes it), so a pass shows both services accept the language
 * and the voice; it does not show how well Prisma understands a person speaking it. Nothing here marks a language "working" by itself:
 * the status badge comes from the results file written by scripts/verify_gnani.py.
 */
export function LanguagesCard({ settings, onChanged }: { settings: PublicSettings; onChanged: () => void }) {
  const { toast } = useToast()
  const langs = useLanguages()
  const [testing, setTesting] = useState<Lang | null>(null)
  const [results, setResults] = useState<Partial<Record<Lang, TestResult | Error>>>({})
  const configured = settings.gnani.configured
  const disabled = new Set<Lang>(settings.languages.disabled)

  const save = async (body: Record<string, unknown>) => {
    try { await api.putSettings(body); toast('Saved.', 'ok'); onChanged(); langs.reload() } catch (e) { toast((e as Error).message, 'bad') }
  }
  const toggle = (o: LangOption, on: boolean) => {
    const next = new Set(disabled)
    if (on) next.delete(o.key); else next.add(o.key)
    void save({ disabled_languages: [...next] })
  }
  const test = async (o: LangOption) => {
    setTesting(o.key)
    try { setResults((r) => ({ ...r, [o.key]: undefined })); const res = await api.testGnani(o.key); setResults((r) => ({ ...r, [o.key]: res })) }
    catch (e) { setResults((r) => ({ ...r, [o.key]: e as Error })) }
    finally { setTesting(null) }
  }

  return (
    <Card title="Languages and voices" description="Choose which languages the Order desk offers and which Timbre voice speaks each one.">
      <ErrorNote error={langs.error} onRetry={langs.reload} />
      {langs.loading && !langs.data && <SkeletonCard lines={6} height={260} />}
      {langs.data && (
        <div className="stack sm">
          <Note tone="info">
            <b>Live status comes from a real run.</b> A language shows "Live checked" only after <code>scripts/verify_gnani.py</code> has passed against Gnani with your key. Until then it says "Not verified live". The connection test below is a loopback: Timbre speaks, Prisma listens to Timbre.
          </Note>
          <ul className="lang-rows" aria-label="Languages">
            {langs.options.map((o) => {
              const info = o.info
              const sum = info ? liveSummary(info.verification) : null
              const r = results[o.key]
              return (
                <li key={o.key} className="lang-row">
                  <div className="lang-row-main">
                    <b lang={htmlLang(o.key)}>{o.native}</b>
                    <span className="muted small">{o.native !== o.name ? `${o.name} · ` : ''}{info ? `${info.stt_code} · Timbre ${info.tts_code}` : ''}</span>
                  </div>
                  <label className="row check tight">
                    <input type="checkbox" checked={o.enabled} disabled={o.key === 'en'} onChange={(e) => toggle(o, e.target.checked)} aria-label={`Offer ${o.name}`} />
                    {o.key === 'en' ? 'Always on' : 'Offered'}
                  </label>
                  {info && (
                    <select aria-label={`${o.name} voice`} value={info.voice} onChange={(e) => void save({ [`tts_voice_${o.key}`]: e.target.value })}>
                      {info.voices.map((v) => <option key={v}>{v}</option>)}
                    </select>
                  )}
                  <span className="lang-row-status">
                    {sum && <Badge tone={LIVE_TONE[sum.state]} title={sum.detail}>{sum.label}</Badge>}
                    <Button variant="secondary" size="sm" onClick={() => void test(o)} disabled={!configured || !o.enabled || testing !== null} loading={testing === o.key}
                            title={configured ? 'Costs 2 Gnani calls' : 'Add a Gnani key first'}>Test (2 calls)</Button>
                  </span>
                  {r instanceof Error && <div className="lang-row-wide"><ErrorNote error={r} /></div>}
                  {r && !(r instanceof Error) && (
                    <div className="lang-row-wide" role="status">
                      <Note tone={r.tts.ok && r.stt.ok ? 'ok' : 'bad'}>
                        <b>{o.name} loopback:</b>{' '}
                        {r.tts.ok ? `voice worked in ${ms(r.tts.latency_ms)}` : `voice failed: ${r.tts.error}`};{' '}
                        {r.stt.ok ? `Prisma heard "${r.stt.transcript}" in ${ms(r.stt.latency_ms)}` : r.tts.ok ? `speech failed: ${r.stt.error}` : 'speech skipped'}.
                        {' '}Spoken by Timbre, not a person.
                      </Note>
                    </div>
                  )}
                </li>
              )
            })}
          </ul>
          <label className="field" htmlFor="sp"><span className="label">Speaking speed ({settings.voices.speed.toFixed(2)}x), all languages</span>
            <input id="sp" type="range" min="0.85" max="1.15" step="0.05" value={settings.voices.speed} onChange={(e) => void save({ tts_speed: Number(e.target.value) })} /></label>
          <p className="muted small" style={{ margin: 0 }}>
            Text-to-speech model: {settings.gnani.tts_model}; speech-to-text model: {settings.gnani.stt_model}. Languages can also be switched off with <code>{settings.languages.env}</code> in the server's .env file.
          </p>
        </div>
      )}
    </Card>
  )
}
