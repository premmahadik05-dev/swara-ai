import { useEffect, useRef, useState } from 'react'
import { Link, useLocation } from 'react-router-dom'
import { Icon } from '../../components/Icons'
import { Logo, LogoMark } from '../../components/Logo'
import { BRAND } from '../../lib/brand'
import { useAuth } from '../../lib/auth'
import { NAV } from './content'

/** Top bar of the public page. Anchors scroll within the page; the two account buttons go to real routes.
 *  Someone who is already signed in sees "Open dashboard" instead of the sign-in and sign-up buttons. */
export function LandingNav() {
  const { status } = useAuth()
  const loc = useLocation()
  const [open, setOpen] = useState(false)
  const toggle = useRef<HTMLButtonElement>(null)

  useEffect(() => { setOpen(false) }, [loc.pathname, loc.hash])
  useEffect(() => {
    if (!open) return
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') { setOpen(false); toggle.current?.focus() } }
    document.addEventListener('keydown', onKey)
    return () => document.removeEventListener('keydown', onKey)
  }, [open])

  const signedIn = status === 'in'
  const account = signedIn
    ? <Link className="btn" to="/dashboard">Open dashboard</Link>
    : <><Link className="btn ghost" to="/sign-in">Sign In</Link><Link className="btn" to="/sign-up">Get Started Free</Link></>

  return (
    <header className="lp-top">
      <div className="lp-bar">
        <Link to="/" className="lp-brand" aria-label={`${BRAND.name}, home`}>
          <Logo decorative height={44} className="lp-logo-full" />
          <LogoMark compact decorative size={36} className="lp-logo-mini" />
        </Link>
        <nav className="lp-links" aria-label="Sections of this page">
          {NAV.map((n) => <a key={n.href} href={n.href}>{n.label}</a>)}
        </nav>
        <span className="grow" />
        <div className="lp-account">{account}</div>
        <button ref={toggle} type="button" className="lp-menu-btn" aria-expanded={open} aria-controls="lp-menu" aria-label={open ? 'Close menu' : 'Open menu'} onClick={() => setOpen((o) => !o)}>
          <Icon name={open ? 'x' : 'menu'} size={20} />
        </button>
      </div>
      {open && (
        <div id="lp-menu" className="lp-menu">
          <nav aria-label="Sections of this page (menu)">
            {NAV.map((n) => <a key={n.href} href={n.href} onClick={() => setOpen(false)}>{n.label}</a>)}
          </nav>
          <div className="lp-menu-account">{account}</div>
        </div>
      )}
    </header>
  )
}
