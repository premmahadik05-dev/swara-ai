import { useEffect, useMemo, useState } from 'react'
import { NavLink, Outlet, useLocation } from 'react-router-dom'
import { api } from '../api/client'
import { useAuth, useSignOut } from '../lib/auth'
import { useDataScope } from '../lib/scope'
import { useHotkey, useAsync } from '../lib/hooks'
import { SHOP_RENAMED } from '../lib/shop'
import { CommandPalette } from './CommandPalette'
import { ErrorBoundary } from './ErrorBoundary'
import { Icon, type IconName } from './Icons'
import { Logo, LogoMark } from './Logo'
import { Avatar, Badge, Button } from './ui'

const GROUPS: { title?: string; items: { to: string; label: string; icon: IconName; ownerOnly?: boolean }[] }[] = [
  { items: [{ to: '/dashboard', label: 'Dashboard', icon: 'dashboard' }, { to: '/order', label: 'Order desk', icon: 'mic' }] },
  { title: 'Sales', items: [{ to: '/orders', label: 'Orders', icon: 'orders' }, { to: '/payments', label: 'Payments', icon: 'wallet' }, { to: '/customers', label: 'Customers', icon: 'users' }] },
  { title: 'Stock', items: [{ to: '/inventory', label: 'Inventory', icon: 'box' }, { to: '/catalogue', label: 'Catalogue', icon: 'catalogue' }] },
  { title: 'Insights', items: [{ to: '/analytics', label: 'Analytics', icon: 'chart' }, { to: '/payment-analytics', label: 'Payment analytics', icon: 'cash', ownerOnly: true }, { to: '/performance', label: 'AI performance', icon: 'trend' }, { to: '/diagnostics', label: 'Voice diagnostics', icon: 'clock', ownerOnly: true }, { to: '/live', label: 'Conversations', icon: 'chat' }] },
  { title: 'Tools', items: [{ to: '/noise', label: 'Noise lab', icon: 'wave' }, { to: '/settings', label: 'Settings', icon: 'gear' }, { to: '/account', label: 'Account', icon: 'user' }] },
]
const ALL = GROUPS.flatMap((g) => g.items)
const COLLAPSE_KEY = 'swara.sidebar'

export function Shell() {
  const health = useAsync(() => api.health(), [], 20000)
  const loc = useLocation()
  const { includeDemo, setIncludeDemo, resolved, setAutoDefault } = useDataScope()
  const { user } = useAuth()
  const signOut = useSignOut()
  const [collapsed, setCollapsed] = useState(() => { try { return localStorage.getItem(COLLAPSE_KEY) === '1' } catch { return false } })
  const [mobileOpen, setMobileOpen] = useState(false)
  const [palette, setPalette] = useState(false)
  // Match whole path segments: '/orders' must not be taken for '/order'.
  const current = ALL.find((t) => loc.pathname === t.to || loc.pathname.startsWith(t.to + '/'))
  const h = health.data

  // With no saved choice, show generated demo records only while the shop has recorded no orders of its own.
  useEffect(() => {
    if (resolved) return
    let live = true
    api.overview(1, false)
      .then((o) => { if (live) setAutoDefault((o?.kpis?.non_synthetic_orders_total ?? 0) === 0) })
      .catch(() => { if (live) setAutoDefault(false) })
    return () => { live = false }
  }, [resolved, setAutoDefault])
  const reloadHealth = health.reload
  useEffect(() => { window.addEventListener(SHOP_RENAMED, reloadHealth); return () => window.removeEventListener(SHOP_RENAMED, reloadHealth) }, [reloadHealth])
  useEffect(() => { setMobileOpen(false) }, [loc.pathname])
  useEffect(() => { document.title = current ? `${current.label} · SWARA AI` : 'SWARA AI' }, [current])
  useHotkey('mod+k', (e) => { e.preventDefault(); setPalette(true) }, true)
  useHotkey('/', (e) => { e.preventDefault(); setPalette(true) })
  const toggleCollapse = () => setCollapsed((c) => { const n = !c; try { localStorage.setItem(COLLAPSE_KEY, n ? '1' : '0') } catch { /* ignore */ } return n })

  const status = useMemo(() => {
    if (health.error) return { tone: 'bad' as const, text: 'Backend offline' }
    if (!h) return { tone: undefined, text: 'Connecting' }
    return h.gnani_configured ? { tone: 'ok' as const, text: 'Voice ready' } : { tone: 'warn' as const, text: 'Typing only' }
  }, [h, health.error])

  return (
    <div className={`app${collapsed ? ' collapsed' : ''}${mobileOpen ? ' nav-open' : ''}`}>
      <a href="#main" className="skip-link">Skip to content</a>
      <div className="nav-scrim" onClick={() => setMobileOpen(false)} aria-hidden />
      <aside className="sidebar" aria-label="Sidebar">
        <div className="sb-top">
          <NavLink to="/dashboard" className="brand" aria-label="SWARA AI, dashboard">
            <Logo compact decorative height={40} className="brand-full" />
            <LogoMark compact decorative size={36} className="brand-mini" />
          </NavLink>
          <Button className="sb-close" variant="ghost" size="sm" iconOnly icon="x" aria-label="Close menu" onClick={() => setMobileOpen(false)} />
        </div>
        <nav aria-label="Main" className="sb-nav">
          {GROUPS.map((g, gi) => (
            <div key={gi} className="sb-group">
              {g.title && <div className="sb-title">{g.title}</div>}
              {g.items.filter((t) => !t.ownerOnly || user?.role === 'owner').map((t) => (
                <NavLink key={t.to} to={t.to} className={({ isActive }) => `sb-link${isActive ? ' active' : ''}`} title={collapsed ? t.label : undefined}>
                  <Icon name={t.icon} size={18} /><span className="sb-label">{t.label}</span>
                </NavLink>
              ))}
            </div>
          ))}
        </nav>
        <div className="sb-foot">
          {user && (
            <div className="sb-user">
              <NavLink to="/account" className="sb-who" title={collapsed ? `${user.full_name}, ${user.role === 'owner' ? 'owner' : 'staff'}` : undefined} aria-label={`Account: ${user.full_name}`}>
                <Avatar name={user.full_name} />
                <span className="sb-label sb-name"><b className="truncate">{user.full_name}</b><span className="xs faint">{user.role === 'owner' ? 'Shop owner' : 'Staff'}</span></span>
              </NavLink>
              <Button className="sb-signout" variant="ghost" size="sm" iconOnly icon="logout" aria-label="Sign out" title="Sign out" onClick={() => { void signOut() }} />
            </div>
          )}
          <div className="sb-status" role="status">
            {h?.store_name && <span className="sb-store truncate" title={h.store_name}>{h.store_name}</span>}
            <Badge tone={status.tone} dot>{status.text}</Badge>
            <span className="sb-note xs faint">{includeDemo ? 'Showing generated demo data' : 'Showing only orders you took'}</span>
          </div>
          <Button className="sb-collapse" variant="ghost" size="sm" icon="panel" onClick={toggleCollapse} aria-pressed={collapsed} aria-label={collapsed ? 'Expand sidebar' : 'Collapse sidebar'}><span className="sb-label">Collapse</span></Button>
        </div>
      </aside>

      <div className="main-col">
        <header className="topbar">
          <Button className="menu-btn" variant="ghost" iconOnly icon="menu" aria-label="Open menu" aria-expanded={mobileOpen} onClick={() => setMobileOpen(true)} />
          <button type="button" className="search-trigger" onClick={() => setPalette(true)} aria-label="Search products, customers, orders (Ctrl+K)">
            <Icon name="search" size={16} /><span className="grow">Search…</span><kbd className="hide-sm">Ctrl K</kbd>
          </button>
          <span className="grow" />
          <label className="switch" title="Demo orders and customers are generated for the demo. Turn off to see only what you recorded.">
            <input type="checkbox" role="switch" checked={includeDemo} onChange={(e) => setIncludeDemo(e.target.checked)} />
            <span className="track" aria-hidden><i /></span>
            <span className="hide-sm">Demo data</span><span className="sr hide-lg-sr">Include demo data</span>
          </label>
        </header>
        <main id="main" className="content" tabIndex={-1}>
          <ErrorBoundary resetKey={loc.pathname}><Outlet /></ErrorBoundary>
        </main>
      </div>
      {palette && <CommandPalette onClose={() => setPalette(false)} />}
    </div>
  )
}
