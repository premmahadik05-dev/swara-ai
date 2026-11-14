import { useEffect, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import { ApiError, api } from '../../api/client'
import { Icon } from '../../components/Icons'
import { Badge } from '../../components/ui'
import { LANG_LATIN, fmtQty, itemName, rupees, unitLabel } from '../../lib/format'
import type { Lang, TurnResponse } from '../../types'
import { EXAMPLES } from './content'

const htmlLang = (l: string) => (l === 'gu' ? 'gu' : l === 'hi' ? 'hi' : 'en')

/** The real language engine, on this server. Posts to /api/text/parse, which stores nothing and reserves no stock. */
export function LiveDemo() {
  const [text, setText] = useState(EXAMPLES[0].text)
  const [res, setRes] = useState<TurnResponse | null>(null)
  const [err, setErr] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const [off, setOff] = useState(false)   // the owner switched the public demo off (PUBLIC_DEMO=false)
  const seq = useRef(0)

  useEffect(() => {
    const t = text.trim()
    if (!t) { setRes(null); setErr(null); return }
    const id = ++seq.current
    setBusy(true)
    const h = setTimeout(() => {
      api.parse(t)
        .then((r) => { if (id === seq.current) { setRes(r); setErr(null) } })
        .catch((e) => {
          if (id !== seq.current) return
          if (e instanceof ApiError && e.code === 'DEMO_OFF') setOff(true)
          else setErr(e.message)
        })
        .finally(() => { if (id === seq.current) setBusy(false) })
    }, 250)
    return () => clearTimeout(h)
  }, [text])

  const lang = (res?.language ?? 'en') as Lang
  const lines = res?.cart.lines ?? []
  const short = lines.filter((l) => Number(l.qty) > l.in_stock)
  // The four steps, filled in from the engine's real answer. Before the first answer they say so, rather than showing a made-up result.
  const steps: { key: string; title: string; text: string; done: boolean }[] = [
    { key: 'heard', title: 'Heard', text: res ? `Read as ${LANG_LATIN[res.language] ?? res.language}` : 'Waiting for a sentence', done: !!res },
    { key: 'found', title: 'Products found', text: !res ? '' : lines.length ? `${lines.length} ${lines.length === 1 ? 'product' : 'products'} matched to the shop's list` : 'No product matched', done: lines.length > 0 },
    { key: 'stock', title: 'Stock checked', text: !res ? '' : !lines.length ? 'Nothing to check' : short.length ? `Not enough in stock: ${short.map((l) => l.name_en).join(', ')}` : 'Enough in stock', done: lines.length > 0 && short.length === 0 },
    { key: 'bill', title: 'Bill prepared', text: !res ? '' : lines.length ? 'Added up, ready to read back' : 'Nothing to add up', done: lines.length > 0 },
  ]
  if (off) {
    return (
      <section className="card card-pad" aria-label="Live language demo">
        <p style={{ margin: 0 }}>
          <b>The live demo is switched off on this server.</b> The owner turned it off so that visitors cannot look through the shop's items and prices.
          {' '}<Link to="/sign-in">Sign in</Link> to use the order desk.
        </p>
      </section>
    )
  }
  return (
    <>
    <section className="card demo-card" aria-label="Live language demo">
      <ol className="demo-steps" aria-label="What the language engine did" aria-live="polite">
        {steps.map((s) => <li key={s.key} data-done={s.done}><b>{s.title}</b><span>{s.text}</span></li>)}
      </ol>
      <div className="demo-in">
        <label className="label" htmlFor="try-text">Type or paste what a customer would say</label>
        <textarea id="try-text" value={text} onChange={(e) => setText(e.target.value)} lang={htmlLang(lang)} />
        <div className="quick">
          {EXAMPLES.map((e) => <button key={e.label} type="button" aria-pressed={text === e.text} onClick={() => setText(e.text)}>{e.label}</button>)}
        </div>
      </div>
      <div className="demo-out" aria-live="polite" aria-busy={busy}>
        {err && <div className="rc-say"><div className="note bad" role="alert"><Icon name="alert" size={17} /><div className="grow">{err}</div></div></div>}
        {!err && res && (
          <>
            <div className="rc">
              <div className="ln head"><span>Heard as</span><span>Quantity</span><span style={{ textAlign: 'right' }}>Amount</span></div>
              {res.cart.lines.map((l) => (
                <div className="ln" key={l.sku}>
                  <span className="nm">{itemName(l, lang)} <span className="muted small">{lang === 'gu' || lang === 'hi' ? l.name_en : ''}</span></span>
                  <span className="q">{fmtQty(l.qty)} {unitLabel(l.unit, lang)}</span>
                  <span className="a">{rupees(l.line_total_paise)}</span>
                </div>
              ))}
              {res.cart.lines.length === 0 && res.parse.lines.map((l, i) => (
                <div className="ln miss" key={i}><span>{l.unknown_term ? `"${l.unknown_term}" is not in this shop` : l.candidates.length > 1 ? `${l.spoken}: ${l.candidates.length} items fit, the assistant would ask which` : l.spoken}</span></div>
              ))}
              {res.cart.lines.length > 0 && <div className="ln total"><span className="nm">Total</span><span /><span className="a">{rupees(res.cart.total_paise)}</span></div>}
            </div>
            <div className="rc-say">
              <div className="row tight">
                <Badge tone="info">{LANG_LATIN[res.language] ?? res.language}</Badge>
                <Badge>intent: {res.parse.intent}</Badge>
                {res.parse.lines.some((l) => l.assumed_default) && <Badge tone="warn">Shop default used</Badge>}
                <Badge>{res.timings.nlu_ms.toFixed(1)} ms</Badge>
              </div>
              <div className="reply" lang={htmlLang(res.reply_lang)}>{res.reply_text}</div>
            </div>
          </>
        )}
        {!err && !res && !busy && <div className="rc-empty">Type something to see it written onto the bill.</div>}
      </div>
    </section>
    <p className="lp-demo-note">A demonstration: typed text only, so no audio is involved. It runs the real language engine on this server, against this shop&rsquo;s stock and prices (generated demo data until you enter your own). Nothing is saved and no stock is reserved.</p>
    </>
  )
}
