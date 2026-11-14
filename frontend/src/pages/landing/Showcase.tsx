import type { ReactNode } from 'react'
import { SHOTS, SHOWCASE, SPECIMEN, VARIANTS } from './content'

type ShotKey = keyof typeof SHOTS

/** A real screenshot of the running app. Only the first picture of the page loads eagerly; the rest wait until they are near the screen. */
export function Shot({ id, eager = false, caption, className }: { id: ShotKey; eager?: boolean; caption?: ReactNode | null; className?: string }) {
  const s = SHOTS[id]
  return (
    <figure className={`lp-shot${className ? ` ${className}` : ''}`}>
      <div className="lp-shot-frame" style={{ aspectRatio: `${s.w} / ${s.h}` }}>
        <img src={s.src} width={s.w} height={s.h} alt={s.alt} decoding="async" {...(eager ? { fetchpriority: 'high' } : { loading: 'lazy' as const })} />
      </div>
      {caption !== null && <figcaption>{caption ?? 'Screenshot of the running app. The shop, customers and orders shown are generated demo data.'}</figcaption>}
    </figure>
  )
}

function Copy({ id, title, children }: { id: string; title: string; children: ReactNode }) {
  return (
    <div className="sw-copy">
      <h3 id={id}>{title}</h3>
      {children}
    </div>
  )
}

/** The five jobs of the product, each with its own composition: a typeset sentence, a spelling ledger, two full screens, and a plain row of notes. */
export function Showcase() {
  const { voice, recognition, inventory, orders, analytics } = SHOWCASE
  return (
    <div className="sw-list">
      {/* 1. voice: type-led, no screenshot */}
      <article className="sw sw-voice" aria-labelledby="sw-voice-h">
        <div className="lp-wrap sw-grid">
          <Copy id="sw-voice-h" title={voice.title}><p>{voice.body}</p></Copy>
          <figure className="spec">
            <ul aria-label="Sample sentences">
              {SPECIMEN.map((s) => (
                <li key={s.language}>
                  <span className="spec-lang">{s.language}</span>
                  <p lang={s.lang}>{s.parts.map((p, i) => (p.mark ? <mark key={i}>{p.t}</mark> : <span key={i}>{p.t}</span>))}</p>
                </li>
              ))}
            </ul>
            <figcaption>Sample sentences, not a recording. The item and quantity the language engine picks out are underlined.</figcaption>
          </figure>
        </div>
      </article>

      {/* 2. recognition: four spellings, one item */}
      <article className="sw sw-recog" aria-labelledby="sw-recog-h">
        <div className="lp-wrap sw-grid">
          <figure className="variants">
            <ul aria-label="Four ways to name one item">
              {VARIANTS.map((v) => (
                <li key={v.text}><span lang={v.lang}>{v.text}</span><small>{v.how}</small></li>
              ))}
            </ul>
            <div className="variants-to"><span className="variants-item">Milk</span><small>one item in the shop&rsquo;s list</small></div>
            <figcaption>Each of the four spellings on the left is matched to the same item by the language engine.</figcaption>
          </figure>
          <Copy id="sw-recog-h" title={recognition.title}><p>{recognition.body}</p></Copy>
        </div>
      </article>

      {/* 3. inventory: a large screen on the left, three facts on the right */}
      <article className="sw sw-stock tint" aria-labelledby="sw-stock-h">
        <div className="lp-wrap sw-grid">
          <Shot id="inventory" />
          <Copy id="sw-stock-h" title={inventory.title}>
            <p>{inventory.body}</p>
            <ul className="sw-points">{inventory.points.map((p) => <li key={p}>{p}</li>)}</ul>
          </Copy>
        </div>
      </article>

      {/* 4. orders: the order desk, with the saved orders list overlapping it */}
      <article className="sw sw-orders" aria-labelledby="sw-orders-h">
        <div className="lp-wrap sw-grid">
          <Copy id="sw-orders-h" title={orders.title}><p>{orders.body}</p></Copy>
          <div className="sw-pair-wrap">
            <div className="sw-pair">
              <Shot id="order-desk" className="sw-pair-a" caption={null} />
              <Shot id="orders" className="sw-pair-b" caption={null} />
            </div>
            <p className="sw-cap">Screenshots of the running app: the Order desk, and the saved orders list. The shop, customers and orders shown are generated demo data.</p>
          </div>
        </div>
      </article>

      {/* 5. analytics: the full width, with the notes underneath */}
      <article className="sw sw-numbers tint" aria-labelledby="sw-numbers-h">
        <div className="lp-wrap">
          <Copy id="sw-numbers-h" title={analytics.title}><p>{analytics.body}</p></Copy>
          <Shot id="analytics" />
          <dl className="sw-notes">
            {analytics.notes.map((n) => <div key={n.title}><dt>{n.title}</dt><dd>{n.body}</dd></div>)}
          </dl>
        </div>
      </article>
    </div>
  )
}
