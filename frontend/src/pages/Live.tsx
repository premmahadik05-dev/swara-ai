import { useEffect, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { api } from '../api/client'
import { Badge, Card, Empty, ErrorNote, PageHeader, SkeletonCard, SkeletonRows } from '../components/ui'
import { LANG_LATIN, fmtQty, itemName, ms, rupees, unitLabel } from '../lib/format'
import { useAsync } from '../lib/hooks'
import type { CartView, Lang, ParsedLineInfo, SessionTurn } from '../types'

interface Exchange { customer: SessionTurn; assistant?: SessionTurn }

function pairs(turns: SessionTurn[]): Exchange[] {
  const out: Exchange[] = []
  for (let i = 0; i < turns.length; i++) {
    if (turns[i].role === 'customer') out.push({ customer: turns[i], assistant: turns[i + 1]?.role === 'assistant' ? turns[i + 1] : undefined })
  }
  return out
}
const htmlLang = (l: string) => (l === 'gu' ? 'gu' : l === 'hi' ? 'hi' : 'en')
const phaseTone = (p: string) => (p === 'completed' ? 'ok' : p === 'cancelled' ? 'bad' : 'info') as 'ok' | 'bad' | 'info'

function StageBar({ stt, nlu, tts }: { stt: number | null; nlu: number | null; tts: number | null }) {
  const parts = [
    { k: 'Speech to text', v: stt, c: 'var(--c1)' },
    { k: 'Understanding', v: nlu, c: 'var(--c2)' },
    { k: 'Spoken reply', v: tts, c: 'var(--c3)' },
  ].filter((p) => p.v)
  const total = parts.reduce((n, p) => n + (p.v ?? 0), 0)
  if (!total) return <span className="muted small">No timing recorded for this turn.</span>
  return (
    <div>
      <div className="stagebar" role="img" aria-label={parts.map((p) => `${p.k} ${ms(p.v)}`).join(', ')}>
        {parts.map((p) => <i key={p.k} style={{ width: `${Math.max(2, ((p.v ?? 0) / total) * 100)}%`, background: p.c }} />)}
      </div>
      <div className="legend">{parts.map((p) => <span key={p.k}><i style={{ background: p.c }} />{p.k} {ms(p.v)}</span>)}</div>
    </div>
  )
}

function LineTable({ lines }: { lines: ParsedLineInfo[] }) {
  if (!lines.length) return <p className="muted small" style={{ margin: 0 }}>No items found in this sentence.</p>
  return (
    <div className="table-wrap">
      <table className="tbl stack-sm">
        <thead><tr><th>Heard</th><th>Matched to</th><th className="num">Quantity</th><th>How sure</th></tr></thead>
        <tbody>
          {lines.map((l, i) => (
            <tr key={i}>
              <td data-label="Heard">{l.spoken || '-'}</td>
              <td data-label="Matched to">
                {l.resolved ? l.candidates[0].name
                  : l.candidates.length > 1 ? <span title={l.candidates.map((c) => c.name).join(', ')}>{l.candidates.length} possible: {l.candidates.slice(0, 3).map((c) => c.name).join(', ')}{l.candidates.length > 3 ? '...' : ''}</span>
                  : l.unknown_term ? <span className="muted">Not in this shop: "{l.unknown_term}"</span> : <span className="muted">No item</span>}
              </td>
              <td className="num" data-label="Quantity">{l.qty_ambiguous ? 'Unclear' : l.qty === null ? '-' : `${l.qty}${l.unit ? ' ' + l.unit : ''}`}</td>
              <td data-label="How sure">
                <span className="row tight">
                  {l.match_kind && <Badge tone={l.match_kind === 'exact' ? 'ok' : 'warn'}>{l.match_kind}{l.match_kind !== 'exact' ? ` ${l.match_score}` : ''}</Badge>}
                  {l.assumed_default && <Badge tone="warn">Shop default</Badge>}
                  {l.candidates.length > 1 && <Badge tone="info">Asks which</Badge>}
                </span>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

/** Read-only receipt of the cart as it stood in this conversation. Editing happens on the Order desk. */
function BillSoFar({ cart, lang }: { cart: CartView; lang: Lang }) {
  return (
    <section className="card bill" aria-label="Bill so far">
      <div className="bill-head"><h2 className="h3">Bill so far</h2><span className="muted small">{cart.lines.length} {cart.lines.length === 1 ? 'item' : 'items'}</span></div>
      <div className="bill-lines">
        {cart.lines.length === 0 ? <Empty title="Nothing on the bill" icon="cart" /> : cart.lines.map((l) => (
          <div key={l.product_id} className="bl" style={{ gridTemplateColumns: 'minmax(0, 1fr) auto auto' }}>
            <div className="nm"><b title={l.name_en}>{itemName(l, lang)}</b><span className="faint xs">{rupees(l.unit_price_paise)} / {unitLabel(l.unit)}</span></div>
            <span className="small muted nowrap">{fmtQty(l.qty)} {unitLabel(l.unit)}</span>
            <span className="amt">{rupees(l.line_total_paise)}</span>
          </div>
        ))}
      </div>
      <div className="bill-foot"><div className="bill-total"><span className="muted">Total</span><span className="big">{rupees(cart.total_paise)}</span></div></div>
    </section>
  )
}

export default function Live() {
  const sessions = useAsync(() => api.sessions(25), [], 3000)
  const latency = useAsync(() => api.latency(), [], 6000)
  const [selected, setSelected] = useState<string | null>(null)
  const ids = sessions.data?.map((s) => s.session_id) ?? []
  useEffect(() => { if (!selected && ids.length) setSelected(ids[0]) }, [ids, selected])
  const detail = useAsync(() => (selected ? api.session(selected) : Promise.reject(new Error('none'))), [selected], selected ? 2500 : undefined)
  const ex = useMemo(() => pairs(detail.data?.turns ?? []), [detail.data])
  const lang = (detail.data?.language ?? 'en') as Lang
  // Names for the reply chips ("added Rice"); a line that has since been removed from the bill falls back to the bare event.
  const nameById = useMemo(() => new Map((detail.data?.cart.lines ?? []).map((l) => [l.product_id, l.name_en])), [detail.data])

  return (
    <>
      <PageHeader title="Conversations" description="Every sentence the assistant hears, how it was understood and how long each step took. This page updates by itself while you take orders."
        meta={<Badge tone="ok" dot>Live, refreshes every few seconds</Badge>} />
      <div className="live-grid">
        <aside className="card" aria-label="Conversations">
          <div className="card-head"><div className="t"><h2 className="h3"><span className="live-dot" aria-hidden />Recent</h2><p>Last 25 conversations</p></div></div>
          <div className="card-body">
            {sessions.loading && !sessions.data && <SkeletonRows rows={5} cols={2} />}
            <ErrorNote error={sessions.error} onRetry={sessions.reload} />
            {sessions.data?.length === 0 && <Empty title="No conversations yet" icon="mic" action={<Link className="btn" to="/order">Open the Order desk</Link>}>Take an order and it appears here.</Empty>}
            <div className="stack tight">
              {sessions.data?.map((s) => (
                <button key={s.session_id} type="button" className="session-btn" onClick={() => setSelected(s.session_id)} aria-pressed={selected === s.session_id}>
                  <span><b>{LANG_LATIN[s.language] ?? s.language}</b> <span className="muted">{s.turns} {s.turns === 1 ? 'turn' : 'turns'}</span></span>
                  <Badge tone={phaseTone(s.phase)}>{s.phase}</Badge>
                </button>
              ))}
            </div>
          </div>
        </aside>

        <div className="stack">
          {!selected && !sessions.loading && <Card><Empty title="Nothing selected" icon="mic">Choose a conversation on the left.</Empty></Card>}
          {selected && detail.error && <ErrorNote error={detail.error} onRetry={detail.reload} />}
          {selected && detail.loading && !detail.data && <Card><SkeletonCard lines={6} height={240} /></Card>}
          {detail.data && (
            <div className="cols two">
              <Card title="Timeline" description="Customer on the left side of the line, assistant replies in gold">
                {ex.length === 0 ? <Empty title="No turns yet" icon="mic" /> : (
                  <div className="timeline">
                    {ex.map((e) => {
                      const parse = e.customer.detail.parse
                      return (
                        <div key={e.customer.id}>
                          <div className="ev">
                            <b lang={htmlLang(e.customer.language)}>"{e.customer.text}"</b>
                            <div className="row tight" style={{ margin: '6px 0' }}>
                              <Badge tone="info">{LANG_LATIN[e.customer.language] ?? e.customer.language}</Badge>
                              <Badge>{e.customer.input_mode === 'voice' || e.customer.input_mode === 'stream' ? 'Spoken' : 'Typed'}</Badge>
                              {parse && <Badge>Intent: {parse.intent}</Badge>}
                            </div>
                            {parse && <LineTable lines={parse.lines} />}
                            <div style={{ marginTop: 8 }}><StageBar stt={e.customer.stt_ms} nlu={e.customer.nlu_ms} tts={e.assistant?.tts_ms ?? null} /></div>
                            {parse && <details><summary>Raw parse</summary><pre className="json">{JSON.stringify(parse, null, 2)}</pre></details>}
                          </div>
                          {e.assistant && (
                            <div className="ev bot">
                              <span lang={htmlLang(e.assistant.language)}>{e.assistant.text}</span>
                              <div className="row tight" style={{ marginTop: 6 }}>
                                {(e.assistant.detail.events ?? []).map((ev, i) => (
                                  <Badge key={i} tone={ev.type === 'out_of_stock' || ev.type === 'unknown' ? 'bad' : ev.type === 'order_created' ? 'ok' : undefined}>{ev.type.replace(/_/g, ' ')}{typeof ev.product_id === 'number' && nameById.get(ev.product_id) ? ` · ${nameById.get(ev.product_id)}` : typeof ev.term === 'string' ? ` · ${ev.term}` : ''}</Badge>
                                ))}
                              </div>
                              {e.assistant.audio_id && <audio controls preload="none" aria-label="Assistant reply audio" src={`/api/audio/${e.assistant.audio_id}`} style={{ marginTop: 8, width: '100%' }} />}
                            </div>
                          )}
                        </div>
                      )
                    })}
                  </div>
                )}
              </Card>
              <div className="stack">
                <BillSoFar cart={detail.data.cart} lang={lang} />
                <Card title="Model calls" description="Last 7 days. Speech times include your network round trip." flush>
                  {latency.data ? (
                    <div className="table-wrap">
                      <table className="tbl dense">
                        <thead><tr><th>Service</th><th className="num">Calls</th><th className="num">p50</th><th className="num">p95</th><th className="num">Errors</th></tr></thead>
                        <tbody>
                          <tr><td><div className="cell-main"><b>Speech to text</b><span className="sub">Gnani Prisma</span></div></td><td className="num">{latency.data['gnani-stt'].calls}</td><td className="num">{ms(latency.data['gnani-stt'].p50_ms)}</td><td className="num">{ms(latency.data['gnani-stt'].p95_ms)}</td><td className="num">{latency.data['gnani-stt'].errors}</td></tr>
                          <tr><td><div className="cell-main"><b>Text to speech</b><span className="sub">Gnani Timbre</span></div></td><td className="num">{latency.data['gnani-tts'].calls}</td><td className="num">{ms(latency.data['gnani-tts'].p50_ms)}</td><td className="num">{ms(latency.data['gnani-tts'].p95_ms)}</td><td className="num">{latency.data['gnani-tts'].errors}</td></tr>
                          <tr><td><div className="cell-main"><b>Order engine</b><span className="sub">Runs here, no network</span></div></td><td className="num">{latency.data.nlu.turns}</td><td className="num">{latency.data.nlu.p50_ms !== null ? `${latency.data.nlu.p50_ms} ms` : '-'}</td><td className="num">{latency.data.nlu.p95_ms !== null ? `${latency.data.nlu.p95_ms} ms` : '-'}</td><td className="num faint" title="Errors are not tracked for the local engine">-</td></tr>
                        </tbody>
                      </table>
                    </div>
                  ) : <div className="card-pad"><SkeletonCard lines={3} /></div>}
                  <p className="muted small card-pad" style={{ margin: 0 }}>Evon is not called: Gnani does not offer it on its public API. A row with 0 calls means no live call has been made from this install.</p>
                </Card>
              </div>
            </div>
          )}
        </div>
      </div>
    </>
  )
}
