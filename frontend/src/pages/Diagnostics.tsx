import { useState } from 'react'
import { Link } from 'react-router-dom'
import { api } from '../api/client'
import { ChartCard, DataTable, HBars } from '../components/charts'
import { GridTable, type GridColumn } from '../components/GridTable'
import { KpiCard } from '../components/Kpi'
import { Badge, Button, Card, Empty, ErrorNote, Note, PageHeader, Seg, SkeletonCard } from '../components/ui'
import { useIsOwner } from '../lib/auth'
import { istTime, ms, pct, plural } from '../lib/format'
import { useAsync } from '../lib/hooks'
import type { GnaniCallStats, SlowTurn, StatSummary, VoiceDiagnostics } from '../types'

const WINDOWS: { value: string; label: string; hours: number }[] = [
  { value: '24', label: '24 hours', hours: 24 },
  { value: '168', label: '7 days', hours: 168 },
  { value: '720', label: '30 days', hours: 720 },
]

const STAGES: { key: 'validate_ms' | 'stt_ms' | 'process_ms' | 'tts_ms'; label: string; note: string }[] = [
  { key: 'validate_ms', label: 'Audio check', note: 'Format and length checks before anything is sent' },
  { key: 'stt_ms', label: 'Speech to text', note: 'The Gnani speech-to-text call, including any retry' },
  { key: 'process_ms', label: 'Order processing', note: 'Understanding the sentence and updating the bill' },
  { key: 'tts_ms', label: 'Spoken reply', note: 'The Gnani text-to-speech call. Zero when the reply was already cached' },
]

const ENDPOINT: Record<string, string> = { auto: 'sent after they stopped talking', manual: 'sent by tapping', live: 'live stream' }

const stat = (s: StatSummary | undefined) => (s && s.n > 0 ? s : null)
const med = (s: StatSummary | undefined) => (s && s.n > 0 && s.p50 !== null ? ms(s.p50) : 'Not measured yet')

const slowColumns: GridColumn<SlowTurn>[] = [
  { key: 'at', label: 'When', value: (r) => r.at, render: (r) => istTime(r.at) },
  { key: 'mode', label: 'Path', value: (r) => r.mode ?? '', render: (r) => (r.mode === 'stream' ? 'Live' : r.mode === 'voice' ? 'Voice' : r.mode ?? '-') },
  { key: 'language', label: 'Language', value: (r) => r.language },
  { key: 'server_ms', label: 'Server total', value: (r) => r.server_ms, render: (r) => ms(r.server_ms), num: true, hint: 'Time inside the server for this turn' },
  { key: 'stt_ms', label: 'Speech to text', value: (r) => r.stt_ms, render: (r) => ms(r.stt_ms), num: true },
  { key: 'process_ms', label: 'Processing', value: (r) => r.process_ms, render: (r) => ms(r.process_ms), num: true },
  { key: 'tts_ms', label: 'Spoken reply', value: (r) => r.tts_ms, render: (r) => (r.tts_cached ? 'Cached' : ms(r.tts_ms)), num: true },
  { key: 'attempts', label: 'Speech attempts', value: (r) => r.stt_attempts, render: (r) => r.stt_attempts ?? '-', num: true, hint: 'More than 1 means the first speech-to-text call was retried' },
  { key: 'reply', label: 'Seen in browser', value: (r) => r.end_to_reply_ms, render: (r) => ms(r.end_to_reply_ms), num: true, hint: 'From the end of speech to the reply on screen, as reported by the browser' },
]

interface ErrorRow { provider: string; type: string; count: number }
const errorColumns: GridColumn<ErrorRow>[] = [
  { key: 'provider', label: 'Service', value: (r) => r.provider },
  { key: 'type', label: 'Error type', value: (r) => r.type },
  { key: 'count', label: 'Calls', value: (r) => r.count, num: true },
]

function Ratio({ s }: { s: GnaniCallStats }) {
  return <>{s.errors} of {plural(s.calls, 'call')}</>
}

function Stats({ d }: { d: VoiceDiagnostics }) {
  const v = d.voice
  const stages = STAGES.map((s) => ({ ...s, sum: v.stages[s.key] }))
  const measured = stages.filter((s) => stat(s.sum) && s.sum.p50 !== null)
  const gnaniRows: ErrorRow[] = [
    ...d.gnani.stt.error_types.map((e) => ({ provider: 'Speech to text', type: e.type, count: e.count })),
    ...d.gnani.tts.error_types.map((e) => ({ provider: 'Text to speech', type: e.type, count: e.count })),
  ]
  const totalErrors = d.gnani.stt.errors + d.gnani.tts.errors
  const totalCalls = d.gnani.stt.calls + d.gnani.tts.calls
  const server = v.stages.server_ms
  const browser = d.browser_reported
  const settingsRows: [string, string][] = [
    ['Gnani key', d.config.gnani_configured ? 'Set on the server' : 'Not set. Voice is off and typing still works'],
    ['Speech-to-text model', d.config.stt_model],
    ['Text-to-speech model', d.config.tts_model],
    ['Speech-to-text timeout', `${d.config.stt_timeout_s} s`],
    ['Text-to-speech timeout', `${d.config.tts_timeout_s} s`],
    ['Connect timeout', `${d.config.connect_timeout_s} s`],
    ['Spoken reply sample rate', `${d.config.tts_sample_rate} Hz`],
    ['Spoken reply speed', String(d.config.tts_speed)],
  ]

  return (
    <>
      <div className="kpi-grid">
        <KpiCard label="Server time per spoken order" icon="clock" value={med(server)}
          foot={stat(server) ? `Slowest 1 in 20: ${ms(server.p95)}. ${plural(v.turns, 'turn')} in this window` : 'No spoken orders recorded in this window'} />
        <KpiCard label="Speech to reply, in the browser" icon="mic" value={med(browser.end_to_reply_ms)}
          foot={stat(browser.end_to_reply_ms) ? `Slowest 1 in 20: ${ms(browser.end_to_reply_ms.p95)}. ${plural(browser.turns, 'turn')} reported` : 'The browser reports this after each spoken order'} />
        <KpiCard label="Speech to text, median" icon="wave" value={med(v.stages.stt_ms)}
          foot={stat(v.stages.stt_ms) ? `Slowest 1 in 20: ${ms(v.stages.stt_ms.p95)}. ${v.retried_speech_calls} retried` : 'Needs a Gnani key and at least one spoken order'} />
        <KpiCard label="Gnani calls that failed" icon="alert" value={totalCalls ? `${totalErrors}` : 'None made'}
          foot={totalCalls ? <>Speech to text: <Ratio s={d.gnani.stt} />. Text to speech: <Ratio s={d.gnani.tts} /></> : 'No speech calls in this window'} />
      </div>

      {v.turns === 0 && (
        <Note tone="info">
          No spoken orders were recorded in this window, so there are no stage times to show. Typed orders are timed separately below.
          Take a spoken order on the <Link to="/order">Order desk</Link> and reload this page.
        </Note>
      )}

      {measured.length > 0 && (
        <ChartCard title="Where the time goes" sub="Median time for each step of a spoken order, measured on the server."
          legend={<span>The steps run one after the other, so the bars add up to the server total. The reply bill is shown as soon as processing ends; the spoken reply follows.</span>}
          table={<DataTable head={['Step', 'Median', 'Slowest 1 in 20', 'Longest', 'Average', 'Turns']}
            rows={stages.map((s) => [s.label, ms(s.sum.p50), ms(s.sum.p95), ms(s.sum.max), ms(s.sum.mean), s.sum.n])} />}>
          <HBars rows={measured.map((s) => ({ name: s.label, v: s.sum.p50 ?? 0 }))} fmt={(n) => ms(n)} labelWidth={140} />
          <ul className="muted small" style={{ margin: '12px 0 0', paddingLeft: 18 }}>
            {stages.map((s) => (
              <li key={s.key}>{s.label}: {s.note}.{v.stage_share_of_median[s.key] !== null && <> About {pct(v.stage_share_of_median[s.key] as number)} of the median.</>}</li>
            ))}
          </ul>
        </ChartCard>
      )}

      <div className="cols even">
        <Card title="Speech calls to Gnani" description="Every call is logged with its time, so these figures are real round trips, not estimates.">
          <div className="table-wrap"><DataTable wrapHead head={['', 'Speech to text', 'Text to speech']} rows={[
            ['Calls', d.gnani.stt.calls, d.gnani.tts.calls],
            ['Succeeded', d.gnani.stt.ok, d.gnani.tts.ok],
            ['Failed', d.gnani.stt.errors, d.gnani.tts.errors],
            ['Needed a retry', d.gnani.stt.retried, d.gnani.tts.retried],
            ['Median time', ms(d.gnani.stt.p50), ms(d.gnani.tts.p50)],
            ['Slowest 1 in 20', ms(d.gnani.stt.p95), ms(d.gnani.tts.p95)],
            ['Longest', ms(d.gnani.stt.max), ms(d.gnani.tts.max)],
          ]} /></div>
          <p className="muted small" style={{ margin: '12px 0 0' }}>
            Calls this hour: {d.budget.calls_last_hour} of the {d.budget.max_per_hour} the shop allows. {pct(v.tts_cached_share ?? 0)} of spoken replies in this window came from the cache.
          </p>
        </Card>

        <Card title="What the browser saw" description="Reported by the browser after each spoken order, so it includes the network.">
          {browser.turns === 0 ? (
            <Empty title="Nothing reported yet" icon="clock">The browser sends these times once a spoken order finishes.</Empty>
          ) : (
            <>
              <div className="table-wrap"><DataTable wrapHead head={['', 'Median', 'Slowest 1 in 20']} rows={[
                ['Speech to reply on screen', ms(browser.end_to_reply_ms.p50), ms(browser.end_to_reply_ms.p95)],
                ['Speech to spoken reply', ms(browser.end_to_audio_ms.p50), ms(browser.end_to_audio_ms.p95)],
                ['Length of speech sent', browser.capture_ms.p50 === null ? '-' : ms(browser.capture_ms.p50), browser.capture_ms.p95 === null ? '-' : ms(browser.capture_ms.p95)],
              ]} /></div>
              {browser.endpoints.length > 0 && (
                <p className="muted small" style={{ margin: '12px 0 0' }}>
                  How recordings ended: {browser.endpoints.map((e) => `${ENDPOINT[e.kind] ?? e.kind} ${e.turns}`).join(', ')}.
                </p>
              )}
            </>
          )}
        </Card>
      </div>

      <Card title="Typed orders" description="Typing skips speech entirely, so this is the order-processing time on its own.">
        {d.typed.turns === 0
          ? <p className="muted small" style={{ margin: 0 }}>No typed orders in this window.</p>
          : <p style={{ margin: 0 }}>Median <b>{ms(d.typed.process_ms.p50)}</b>, slowest 1 in 20 <b>{ms(d.typed.process_ms.p95)}</b>, across {plural(d.typed.turns, 'order')}.</p>}
      </Card>

      <Card title="Slowest spoken orders" description="The ten slowest turns in this window, longest first. Sort or search to find a pattern." flush>
        <GridTable rows={d.slowest} columns={slowColumns} rowKey={(r) => String(r.turn_id)} noun="turns" exportName="slowest-voice-turns" pageSize={10}
          initialSort={{ key: 'server_ms', dir: 'desc' }}
          empty={<Empty title="No spoken orders to rank" icon="clock">Spoken orders appear here once they have been taken.</Empty>} />
      </Card>

      {gnaniRows.length > 0 && (
        <Card title="Failed Gnani calls by type" description="What went wrong, so you can tell a network problem from a key problem." flush>
          <GridTable rows={gnaniRows} columns={errorColumns} rowKey={(r) => `${r.provider}:${r.type}`} noun="error types" exportName="gnani-error-types" pageSize={10} />
        </Card>
      )}

      <Card title="Settings in use" description="Read from the server's configuration. Change the timeouts in the .env file; see docs/GNANI_SETUP.md.">
        <div className="table-wrap">
          <table className="tbl compact">
            <thead><tr><th>Setting</th><th>Value</th></tr></thead>
            <tbody>
              {settingsRows.map(([k, v]) => (<tr key={k}><td>{k}</td><td>{v}</td></tr>))}
            </tbody>
          </table>
        </div>
      </Card>

      <Note tone="warn">
        <b>What this page can and cannot tell you.</b> The times come from the spoken orders this shop has actually taken, so they reflect your network and your Gnani account.
        The reply bill appears as soon as processing ends and the spoken reply is requested separately; that shortens the wait for the bill, not the time until the voice plays.
        Accuracy of the recognised speech is a different question and is not measured here.
      </Note>
    </>
  )
}

export default function Diagnostics() {
  const owner = useIsOwner()
  const [win, setWin] = useState('168')
  const hours = WINDOWS.find((w) => w.value === win)?.hours ?? 168
  const q = useAsync(() => (owner ? api.voiceDiagnostics(hours) : Promise.resolve(null)), [owner, hours])

  if (!owner) {
    return (
      <>
        <PageHeader title="Voice diagnostics" description="Response time for spoken orders." />
        <Empty title="Only the shop owner can open this page" icon="lock">Ask the owner to look at the timings, or sign in with the owner account.</Empty>
      </>
    )
  }

  return (
    <>
      <PageHeader title="Voice diagnostics"
        description="How long each step of a spoken order took, measured on the server for orders this shop has taken. Owner only."
        meta={q.data ? <><Badge>Last {WINDOWS.find((w) => w.value === win)?.label}</Badge><Badge>Updated {istTime(q.data.generated_at)}</Badge></> : undefined}
        actions={<Button variant="secondary" size="sm" icon="refresh" onClick={q.reload}>Refresh</Button>} />
      <div className="stack">
        <div className="toolbar" style={{ borderBottom: 0, padding: 0 }}>
          <div className="field"><span className="label">Period</span>
            <Seg label="Period" value={win} onChange={setWin} options={WINDOWS.map((w) => ({ value: w.value, label: w.label }))} />
          </div>
        </div>
        <ErrorNote error={q.error} onRetry={q.reload} />
        {q.loading && !q.data && <SkeletonCard lines={6} height={300} />}
        {q.data && <Stats d={q.data} />}
      </div>
    </>
  )
}
