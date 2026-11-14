import { useEffect, type ReactNode } from 'react'
import { Link, useLocation } from 'react-router-dom'
import { Icon } from '../components/Icons'
import { Logo } from '../components/Logo'
import { BRAND } from '../lib/brand'
import { useAuth } from '../lib/auth'
import { FAQ, FLOW, LANGUAGES, NEW_LANGUAGES, SECURITY, SECURITY_LIMITS, SHOTS, STACK, TECH, WHY, type TechStatus } from './landing/content'
import { ContactForm } from './landing/ContactForm'
import { LanguageShowcase } from './landing/LanguageShowcase'
import { LandingNav } from './landing/Nav'
import { LiveDemo } from './landing/LiveDemo'
import { Showcase } from './landing/Showcase'

/** A page section: the heading on the left and the short lead beside it, then the content. `split` puts the heading in a narrow left column
 *  with the content to its right (used where the content is a long list). */
function Section({ id, title, lead, tone = 'plain', split = false, children }: { id: string; title: string; lead?: ReactNode; tone?: 'plain' | 'tint'; split?: boolean; children: ReactNode }) {
  return (
    <section id={id} className={`lp-section${tone === 'tint' ? ' tint' : ''}${split ? ' split' : ''}`} aria-labelledby={`${id}-h`}>
      <div className="lp-wrap lp-section-grid">
        <div className="lp-head">
          <h2 id={`${id}-h`}>{title}</h2>
          {lead && <p className="lp-lead">{lead}</p>}
        </div>
        <div className="lp-body">{children}</div>
      </div>
    </section>
  )
}

const GROUPS: { title: string; icon: 'check' | 'shield' | 'minus'; note: string; match: TechStatus[] }[] = [
  { title: 'Working in this release', icon: 'check', note: 'Built, and covered by the automated tests.', match: ['working'] },
  { title: 'Works once you add credentials', icon: 'shield', note: 'Built; needs a key or server settings that only you can provide.', match: ['key', 'config'] },
  { title: 'Not built', icon: 'minus', note: 'Not part of this product today.', match: ['none'] },
]

/** Fragment links (`/#contact`) from other pages land on the right section; plain in-page anchors are handled by the browser. */
function useScrollToHash() {
  const { hash } = useLocation()
  useEffect(() => {
    if (!hash) return
    const el = document.getElementById(decodeURIComponent(hash.slice(1)))
    el?.scrollIntoView?.({ block: 'start' })
  }, [hash])
}

export default function Landing() {
  const { status } = useAuth()
  const signedIn = status === 'in'
  useScrollToHash()
  useEffect(() => { document.title = `${BRAND.name}: ${BRAND.tagline}` }, [])

  const hero = SHOTS.dashboard
  return (
    <div className="land">
      <a href="#main" className="skip-link">Skip to content</a>
      <LandingNav />

      <main id="main" tabIndex={-1}>
        <section className="lp-hero" aria-labelledby="hero-h">
          <div className="lp-wrap">
            <div className="lp-hero-top">
              <h1 id="hero-h">{BRAND.headline}</h1>
              <div className="lp-hero-side">
                <p className="lp-hero-lead">{BRAND.lead}</p>
                <div className="row lp-cta">
                  {signedIn ? <Link className="btn large" to="/dashboard">Open dashboard</Link> : <Link className="btn large" to="/sign-up">Get Started Free</Link>}
                  <a className="btn secondary large" href="#product">Explore the Platform</a>
                </div>
              </div>
            </div>
            <p className="lp-langs" aria-label="Languages: Gujarati, Hindi, English, Hinglish, Marathi, Bengali, Tamil, Telugu, Kannada, Malayalam and Punjabi">
              {[...LANGUAGES, ...NEW_LANGUAGES].map((l) => <span key={l.name} lang={l.lang}>{l.script}</span>)}
            </p>
          </div>
          <div className="lp-stage">
            <div className="lp-wrap">
              <figure className="lp-shot lp-hero-shot">
                <div className="lp-shot-frame" style={{ aspectRatio: `${hero.w} / ${hero.h}` }}>
                  <img src={hero.src} width={hero.w} height={hero.h} alt={hero.alt} decoding="async" {...{ fetchpriority: 'high' }} />
                </div>
                <figcaption>The dashboard of the running app. The numbers shown are generated demo data, not a real shop. <a href={hero.src} target="_blank" rel="noopener">Open full size</a></figcaption>
              </figure>
            </div>
          </div>
        </section>

        <section id="about" className="lp-about" aria-labelledby="about-h">
          <div className="lp-wrap">
            <h2 id="about-h" className="sr">About {BRAND.name}</h2>
            <p className="lp-statement">{BRAND.about}</p>
            <ul className="pillars" aria-label="What we focus on">
              {BRAND.pillars.map((p) => <li key={p}>{p}</li>)}
            </ul>
          </div>
        </section>

        <section id="product" className="lp-product" aria-labelledby="product-h">
          <div className="lp-wrap">
            <div className="lp-head">
              <h2 id="product-h">Everything a counter needs, nothing it does not</h2>
              <p className="lp-lead">Five things the software does today, each shown on the running app.</p>
            </div>
          </div>
          <Showcase />
        </section>

        <Section id="how-it-works" title="How it works"
                 lead="A customer says it. SWARA AI understands it, finds the products, checks the shelf and prepares the bill. Type a sentence to watch each step on the real language engine.">
          <LiveDemo />
        </Section>

        <Section id="languages" tone="tint" title="Eleven ways to place the same order"
                 lead="Choose a language on the Order desk, speak or type, and the bill and the reply come back in it. The text engine reads each script and mixes them within a sentence. Other Indian languages are not supported.">
          <LanguageShowcase />
        </Section>

        <Section id="technology" title="Technology, and what is not built"
                 lead="Stated plainly so nobody has to find out later. Speech recognition and the spoken reply are Gnani AI services; everything else runs on your own server.">
          <ol className="lp-flow" aria-label="How the parts connect">
            {FLOW.map((f) => <li key={f.title}><b>{f.title}</b><span>{f.body}</span></li>)}
          </ol>
          <dl className="lp-stack">
            {STACK.map((s) => <div key={s.part}><dt>{s.part}</dt><dd>{s.what}</dd></div>)}
          </dl>
          <div className="lp-tech">
            {GROUPS.map((g) => (
              <div key={g.title} className={`lp-tech-col ${g.match[0]}`}>
                <h3><Icon name={g.icon} size={17} />{g.title}</h3>
                <p className="muted small">{g.note}</p>
                <ul>
                  {TECH.filter((t) => g.match.includes(t.status)).map((t) => (
                    <li key={t.area}><b>{t.area}</b><span>{t.what}</span></li>
                  ))}
                </ul>
              </div>
            ))}
          </div>
          <p className="muted small lp-foot-note">The automated tests exercise the speech features against a local stand-in for Gnani, not the live service, so this page makes no claim about speech accuracy. Speech depends on your key and on Gnani.</p>
        </Section>

        <Section id="security" tone="tint" split title="Security and trust"
                 lead="What protects an account and a shop's records, taken from what the code does. Nothing here is a promise about things we have not built.">
          <ul className="lp-security">
            {SECURITY.map((b) => (
              <li key={b.title}>
                <h3>{b.title}</h3>
                <p>{b.body}</p>
              </li>
            ))}
          </ul>
          <p className="lp-limits"><Icon name="info" size={17} /><span><b>What we do not claim. </b>{SECURITY_LIMITS}</span></p>
        </Section>

        <Section id="why" title="Why SWARA AI">
          <dl className="lp-why">
            {WHY.map((w) => <div key={w.title}><dt>{w.title}</dt><dd>{w.body}</dd></div>)}
          </dl>
        </Section>

        <Section id="faq" tone="tint" split title="Questions, answered">
          <div className="lp-faq">
            {FAQ.map((f) => (
              <details key={f.q}>
                <summary><span>{f.q}</span><Icon name="chevronDown" size={18} /></summary>
                <p>{f.a}</p>
              </details>
            ))}
          </div>
        </Section>

        <section id="contact" className="lp-section lp-final" aria-labelledby="contact-h">
          <div className="lp-wrap lp-contact">
            <div>
              <h2 id="contact-h">Talk to us, or start now</h2>
              <p className="lp-lead">Ask a question, request a demo, or create an account and try the Order desk yourself.</p>
              <div className="row lp-cta">
                {signedIn ? <Link className="btn large" to="/dashboard">Open dashboard</Link> : <><Link className="btn large" to="/sign-up">Get Started Free</Link><Link className="btn secondary large" to="/sign-in">Sign In</Link></>}
              </div>
            </div>
            <ContactForm />
          </div>
        </section>
      </main>

      <footer className="lp-foot">
        <div className="lp-wrap lp-foot-grid">
          <div className="lp-foot-brand">
            <Link to="/" aria-label={`${BRAND.name}, home`}><Logo height={40} decorative /></Link>
            <p>{BRAND.tagline}</p>
            <p className="muted small">Speech recognition by Gnani.ai Prisma, spoken replies by Gnani.ai Timbre. SWARA AI is not affiliated with or endorsed by Gnani.ai.</p>
          </div>
          <nav aria-label="Product"><h2>Product</h2><a href="#product">Product</a><a href="#how-it-works">How it works</a><a href="#languages">Languages</a><a href="#technology">Technology</a><a href="#security">Security</a></nav>
          <nav aria-label="Resources"><h2>Resources</h2><a href="/docs">API reference</a><a href="#faq">FAQ</a><a href="#contact">Contact</a></nav>
          <nav aria-label="Legal"><h2>Legal</h2><Link to="/terms">Terms of Use</Link><Link to="/privacy">Privacy Policy</Link></nav>
          <nav aria-label="Account"><h2>Account</h2>{signedIn ? <><Link to="/dashboard">Dashboard</Link><Link to="/account">Your account</Link></> : <><Link to="/sign-in">Sign In</Link><Link to="/sign-up">Get Started Free</Link></>}</nav>
        </div>
        <div className="lp-wrap lp-legal-wrap"><div className="lp-legal"><span>© 2026 {BRAND.name}</span></div></div>
      </footer>
    </div>
  )
}
