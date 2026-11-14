import { useEffect, useRef, useState } from 'react'
import { api } from '../api/client'
import { ChartCard, DataTable, HBars } from '../components/charts'
import { useToast } from '../components/Toast'
import { Badge, Button, Card, ErrorNote, Field, Note, PageHeader, Seg } from '../components/ui'
import { MicError, WavRecorder, decodeToMono16k, encodeWav } from '../lib/audio'
import { ms } from '../lib/format'
import { useAsync } from '../lib/hooks'
import type { NoiseCondition, NoiseRow } from '../types'

type Kind = NonNullable<NoiseCondition['kind']>
const KINDS: { id: Kind; label: string; hint: string }[] = [
  { id: 'white', label: 'Hiss', hint: 'White noise: fan, static' },
  { id: 'pink', label: 'Rumble', hint: 'Pink noise: traffic, wind' },
  { id: 'babble', label: 'Crowd', hint: 'Speech-shaped babble, synthetic' },
  { id: 'hum', label: 'Mains hum', hint: '50 Hz hum and harmonics' },
]
const SNRS = [20, 10, 5, 0]
const MAX = 8
const MAX_S = 28

const condLabel = (c: NoiseCondition) => {
  const k = c.kind ? `${KINDS.find((x) => x.id === c.kind)?.label} at ${c.snr_db} dB` : ''
  return [k, c.telephony ? 'phone line' : ''].filter(Boolean).join(' + ')
}
const pct = (v: number | null | undefined) => (v == null ? '-' : `${Math.round(v * 100)}%`)

export default function NoiseLab() {
  const { toast } = useToast()
  const health = useAsync(() => api.health(), [])
  const keySet = health.data?.gnani_configured ?? false

  const [clip, setClip] = useState<{ wav: Blob; seconds: number; url: string; source: string } | null>(null)
  const [recording, setRecording] = useState(false)
  const [level, setLevel] = useState(0)
  const [language, setLanguage] = useState<'gu' | 'hi' | 'en'>('gu')
  const [reference, setReference] = useState('')
  const [conds, setConds] = useState<NoiseCondition[]>([])
  const [kind, setKind] = useState<Kind>('babble')
  const [snr, setSnr] = useState(10)
  const [tel, setTel] = useState(false)
  const [previews, setPreviews] = useState<Record<string, { url: string; measured: string | null }>>({})
  const [busy, setBusy] = useState<'run' | 'preview' | null>(null)
  const [rows, setRows] = useState<NoiseRow[] | null>(null)
  const [ranWith, setRanWith] = useState<{ ref: string; lang: string } | null>(null)
  const [err, setErr] = useState<Error | null>(null)
  const rec = useRef<WavRecorder | null>(null)
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null)
  const urls = useRef<string[]>([])

  useEffect(() => () => { urls.current.forEach((u) => URL.revokeObjectURL(u)); if (timer.current) clearTimeout(timer.current); void rec.current?.stop().catch(() => undefined) }, [])

  const setNewClip = (wav: Blob, seconds: number, source: string) => {
    if (clip) URL.revokeObjectURL(clip.url)
    const url = URL.createObjectURL(wav)
    urls.current.push(url)
    setClip({ wav, seconds, url, source })
    setPreviews({}); setRows(null)
  }

  const stop = async () => {
    if (timer.current) clearTimeout(timer.current)
    const r = rec.current
    rec.current = null
    setRecording(false); setLevel(0)
    if (!r) return
    try {
      const out = await r.stop()
      if (out.seconds < 0.4) toast('That was too short. Hold the button and say the whole order.', 'info')
      else if (out.peak < 0.02) toast('The recording is almost silent. Check the microphone and try again.', 'bad')
      else setNewClip(out.wav, out.seconds, 'Recorded here')
    } catch (e) { setErr(e as Error) }
  }
  const start = async () => {
    setErr(null)
    const r = new WavRecorder(setLevel)
    try {
      await r.start()
      rec.current = r
      setRecording(true)
      timer.current = setTimeout(() => void stop(), MAX_S * 1000)
    } catch (e) { setErr(e instanceof MicError ? new Error(e.message) : (e as Error)) }
  }
  const onFile = async (f: File | undefined) => {
    if (!f) return
    setErr(null)
    try {
      const pcm = await decodeToMono16k(f)
      if (pcm.length / 16000 > MAX_S) throw new Error(`That clip is longer than ${MAX_S} seconds. Trim it first.`)
      setNewClip(encodeWav(pcm), pcm.length / 16000, f.name)
    } catch (e) { setErr(e as Error) }
  }

  const add = () => {
    const c: NoiseCondition = { kind, snr_db: snr, telephony: tel }
    if (conds.some((x) => x.kind === c.kind && x.snr_db === c.snr_db && x.telephony === c.telephony)) { toast('That condition is already in the list.', 'info'); return }
    if (conds.length >= MAX) { toast(`At most ${MAX} conditions per run, to protect your API budget.`, 'info'); return }
    setConds([...conds, c]); setRows(null)
  }
  const addPhone = () => {
    const c: NoiseCondition = { kind: null, snr_db: null, telephony: true }
    if (conds.some((x) => !x.kind && x.telephony)) return
    if (conds.length >= MAX) return
    setConds([...conds, c]); setRows(null)
  }
  const key = (c: NoiseCondition) => `${c.kind}|${c.snr_db}|${c.telephony}`

  const listen = async (c: NoiseCondition) => {
    if (!clip) return
    setBusy('preview'); setErr(null)
    try {
      const p = await api.noisePreview(clip.wav, c)
      urls.current.push(p.url)
      setPreviews((m) => ({ ...m, [key(c)]: p }))
    } catch (e) { setErr(e as Error) } finally { setBusy(null) }
  }
  const run = async () => {
    if (!clip || !conds.length) return
    setBusy('run'); setErr(null); setRows(null)
    try {
      const r = await api.noiseRun(clip.wav, conds, language, reference)
      setRows(r.results); setRanWith({ ref: reference.trim(), lang: language })
    } catch (e) { setErr(e as Error) } finally { setBusy(null) }
  }

  const hasRef = !!ranWith?.ref
  const chartRows = (rows ?? []).filter((r) => r.wer != null).map((r) => ({ label: r.label, wer: Math.round((r.wer ?? 0) * 100) }))
  const calls = conds.length + 1

  return (
    <>
      <PageHeader title="Noise lab" description="Hear how a noisy shop affects speech recognition, using your own voice." />
      <div className="stack">
        <Note>
          <b>How this works.</b> Record or upload one order. The server adds noise at the signal-to-noise ratio you choose, plays it back for you to hear, and sends each version to Gnani Prisma. You see what it heard and what the shop system understood. Noise here is generated by code, so treat results as a stress test, not a field measurement.
        </Note>
        <ErrorNote error={err} />

        <div className="cols two">
          <Card title="1. Your clip" description={`Say one order. Up to ${MAX_S} seconds.`}>
            <div className="row">
              <Button variant={recording ? 'solid-danger' : 'primary'} icon="mic" onClick={recording ? stop : start}>{recording ? 'Stop recording' : 'Record a clip'}</Button>
              <label className="btn secondary" style={{ cursor: 'pointer' }}>
                Upload audio
                <input type="file" accept="audio/*" hidden onChange={(e) => { void onFile(e.target.files?.[0]); e.target.value = '' }} />
              </label>
              {recording && <div className="meter grow" aria-hidden><i style={{ width: `${Math.min(100, level * 140)}%` }} /></div>}
            </div>
            {clip ? (
              <div className="stack sm" style={{ marginTop: 14 }}>
                <div className="row"><Badge tone="ok">{clip.seconds.toFixed(1)} s</Badge><span className="muted small">{clip.source}</span></div>
                <audio controls src={clip.url} style={{ width: '100%' }} aria-label="Original clip" />
              </div>
            ) : <p className="muted small" style={{ marginTop: 12, marginBottom: 0 }}>For example: "do kilo chawal aur ek litre doodh".</p>}
            <div className="grid2" style={{ marginTop: 16 }}>
              <Field label="Language you spoke" htmlFor="nl">
                <select id="nl" value={language} onChange={(e) => setLanguage(e.target.value as 'gu' | 'hi' | 'en')}>
                  <option value="gu">Gujarati</option><option value="hi">Hindi / Hinglish</option><option value="en">English</option>
                </select>
              </Field>
              <Field label="What you said (optional)" htmlFor="nr">
                <input id="nr" type="text" value={reference} onChange={(e) => setReference(e.target.value)} placeholder="Type it to get error rates" maxLength={400} />
              </Field>
            </div>
          </Card>

          <Card title="2. Add noise" description="Pick a type and how loud it is, then add it to the list">
            <div className="stack sm">
              <Seg<Kind> label="Noise type" value={kind} onChange={setKind} options={KINDS.map((k) => ({ value: k.id, label: k.label }))} />
              <p className="muted small" style={{ margin: 0 }}>{KINDS.find((k) => k.id === kind)?.hint}</p>
              <div className="field">
                <span className="label">How loud compared with your voice</span>
                <Seg<string> label="Signal to noise ratio" value={String(snr)} onChange={(v) => setSnr(Number(v))} options={SNRS.map((n) => ({ value: String(n), label: `${n} dB` }))} />
                <span className="hint">20 dB is a quiet shop. 0 dB means the noise is as loud as you.</span>
              </div>
              <label className="check"><input type="checkbox" checked={tel} onChange={(e) => setTel(e.target.checked)} /> Also squeeze to a phone line (300 to 3400 Hz)</label>
              <div className="row">
                <Button onClick={add}>Add this condition</Button>
                <Button variant="secondary" onClick={addPhone}>Add phone line only</Button>
              </div>
            </div>
          </Card>
        </div>

        <Card title="3. Conditions to test" description="The clean clip is always tested first as the baseline">
          {conds.length === 0 ? <p className="muted" style={{ margin: 0 }}>Nothing added yet.</p> : (
            <ul className="list-rows">
              {conds.map((c) => {
                const p = previews[key(c)]
                return (
                  <li key={key(c)} style={{ flexWrap: 'wrap' }}>
                    <b className="grow">{condLabel(c)}</b>
                    {p && <><audio controls src={p.url} style={{ height: 36 }} aria-label={`Preview: ${condLabel(c)}`} />{p.measured && <span className="muted small">measured {p.measured} dB</span>}</>}
                    <Button variant="secondary" size="sm" disabled={!clip || busy !== null} onClick={() => void listen(c)}>Listen</Button>
                    <Button variant="ghost" size="sm" aria-label={`Remove ${condLabel(c)}`} onClick={() => { setConds(conds.filter((x) => key(x) !== key(c))); setRows(null) }}>Remove</Button>
                  </li>
                )
              })}
            </ul>
          )}
          <div className="row" style={{ marginTop: 16 }}>
            <Button disabled={!clip || !conds.length || busy !== null || !keySet} loading={busy === 'run'} onClick={() => void run()}>
              {busy === 'run' ? 'Testing with Gnani…' : `Run on Gnani Prisma (${calls} ${calls === 1 ? 'call' : 'calls'})`}
            </Button>
            {!keySet && <Badge tone="warn">Add your Gnani key in Settings first</Badge>}
            {!clip && <span className="muted small">Record or upload a clip first.</span>}
          </div>
        </Card>

        {rows && (
          <Card title="Results" description={`Spoken language sent to Prisma: ${ranWith?.lang}. Real Gnani responses for your clip; the added noise is generated by code.`} flush>
            <div className="table-wrap" aria-live="polite">
              <table className="tbl">
                <thead><tr><th>Condition</th><th className="num">Measured SNR</th><th>What Prisma heard</th><th>What the shop understood</th>{hasRef && <th className="num">Word errors</th>}{hasRef && <th className="num">Letter errors</th>}<th className="num">Time</th></tr></thead>
                <tbody>
                  {rows.map((r) => (
                    <tr key={r.label}>
                      <td><b>{r.label}</b></td>
                      <td className="num">{r.measured_snr_db == null ? '-' : `${r.measured_snr_db} dB`}</td>
                      <td>{r.error ? <span className="bad-text">{r.error}</span> : (r.transcript || <span className="muted">Nothing heard</span>)}</td>
                      <td>{r.parsed_lines?.length ? r.parsed_lines.map((l, i) => (<div key={i}>{l.product ?? <i>unclear: {l.spoken}</i>}{l.qty != null && ` × ${l.qty}${l.unit ? ' ' + l.unit : ''}`}</div>)) : <span className="muted">-</span>}</td>
                      {hasRef && <td className="num">{pct(r.wer)}</td>}
                      {hasRef && <td className="num">{pct(r.cer)}</td>}
                      <td className="num">{ms(r.latency_ms)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            {hasRef && chartRows.length > 0 && (
              <div className="card-pad">
                <ChartCard title="Word error rate by condition" sub="Lower is better. One clip, one run: it shows direction, not a benchmark."
                  table={<DataTable head={['Condition', 'Word errors']} rows={chartRows.map((r) => [r.label, `${r.wer}%`])} />}>
                  <HBars rows={chartRows.map((r) => ({ name: r.label, v: r.wer }))} fmt={(n) => `${n}%`} labelWidth={190} />
                </ChartCard>
              </div>
            )}
          </Card>
        )}
      </div>
    </>
  )
}
