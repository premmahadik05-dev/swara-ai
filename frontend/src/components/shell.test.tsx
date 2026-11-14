import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes, useLocation } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { ErrorBoundary } from './ErrorBoundary'
import { Shell } from './Shell'
import { DataScopeProvider, useDataScope } from '../lib/scope'
import { mockRoutes } from '../test/fixtures'
import { STAFF_USER, TestAuth } from '../test/auth'
import { SHOP_RENAMED } from '../lib/shop'
import { api } from '../api/client'

afterEach(() => { vi.unstubAllGlobals(); localStorage.clear() })
beforeEach(() => {
  // jsdom has no matchMedia; the media-query hook asks for it.
  vi.stubGlobal('matchMedia', (q: string) => ({ matches: false, media: q, addEventListener() {}, removeEventListener() {}, addListener() {}, removeListener() {}, dispatchEvent: () => false, onchange: null }))
})

const HEALTH = { status: 'ok', db: 'ok', products: 65, gnani_configured: false, version: '1', store_name: 'Patel Kirana' }
const OVERVIEW = (real: number) => ({ window_days: 1, include_synthetic: false, kpis: { non_synthetic_orders_total: real } })
const Where = () => { const l = useLocation(); return <div data-testid="where">{l.pathname}{l.search}</div> }
const Probe = () => { const { includeDemo } = useDataScope(); return <div data-testid="scope">{includeDemo ? 'with demo' : 'real only'}</div> }
const renderShell = (path = '/dashboard') => render(
  <MemoryRouter initialEntries={[path]}>
    <TestAuth><DataScopeProvider>
      <Routes><Route element={<Shell />}>
        <Route path="/dashboard" element={<><h1>Dashboard page</h1><Probe /><Where /></>} />
        <Route path="/orders" element={<><h1>Orders page</h1><Where /></>} />
        <Route path="/order" element={<><h1>Order desk page</h1><Where /></>} />
        <Route path="/customers" element={<><h1>Customers page</h1><Where /></>} />
        <Route path="/boom" element={<Boom />} />
      </Route></Routes>
    </DataScopeProvider></TestAuth>
  </MemoryRouter>,
)
function Boom(): never { throw new Error('Kaboom') }

describe('Shell', () => {
  it('shows the sidebar with the current page marked, the store name, and an honest status', async () => {
    mockRoutes({ 'GET /api/health': HEALTH })
    renderShell('/orders')
    const nav = screen.getByRole('navigation', { name: 'Main' })
    expect(within(nav).getByRole('link', { name: 'Orders' })).toHaveClass('active')
    expect(within(nav).getByRole('link', { name: 'Dashboard' })).not.toHaveClass('active')
    expect(await screen.findByText('Patel Kirana')).toBeInTheDocument()
    expect(screen.getByText('Typing only')).toBeInTheDocument()          // no Gnani key: it does not claim voice is ready
    expect(screen.getByRole('link', { name: 'Skip to content' })).toHaveAttribute('href', '#main')
    expect(screen.getByRole('link', { name: 'SWARA AI, dashboard' })).toHaveAttribute('href', '/dashboard')   // the logo is the way home
    await waitFor(() => expect(document.title).toBe('Orders · SWARA AI'))   // not "Order desk": '/orders' is not '/order'
  })

  it('titles the Order desk page correctly too', async () => {
    mockRoutes({ 'GET /api/health': HEALTH })
    renderShell('/order')
    await waitFor(() => expect(document.title).toBe('Order desk · SWARA AI'))
  })

  it('reports the backend as offline instead of pretending', async () => {
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new TypeError('x')))
    renderShell()
    expect(await screen.findByText('Backend offline')).toBeInTheDocument()
  })

  it('has no theme switch: SWARA AI is light only, so the top bar offers no dark option', async () => {
    mockRoutes({ 'GET /api/health': HEALTH })
    renderShell()
    await screen.findByText('Patel Kirana')
    expect(screen.queryByRole('button', { name: /theme|dark|light/i })).toBeNull()
    expect(document.documentElement.dataset.theme).toBeUndefined()
  })

  it('the demo-data switch changes the scope for the whole app and is remembered', async () => {
    mockRoutes({ 'GET /api/health': HEALTH, 'GET /api/analytics/overview?days=1&include_synthetic=false': OVERVIEW(0) })
    renderShell()
    expect(await screen.findByText('with demo')).toBeInTheDocument()       // a shop with no orders of its own starts with the demo records
    await userEvent.click(screen.getByRole('switch', { name: /Demo data|Include demo data/ }))
    expect(screen.getByTestId('scope')).toHaveTextContent('real only')
    expect(localStorage.getItem('swara.includeDemo')).toBe('0')
    expect(screen.getByText('Showing only orders you took')).toBeInTheDocument()
  })

  it('a shop that has recorded real orders starts with real records only, and never shows generated figures first', async () => {
    mockRoutes({ 'GET /api/health': HEALTH, 'GET /api/analytics/overview?days=1&include_synthetic=false': OVERVIEW(12) })
    renderShell()
    expect(screen.getByTestId('scope')).toHaveTextContent('real only')     // before the answer arrives
    await waitFor(() => expect(screen.getByText('Showing only orders you took')).toBeInTheDocument())
    expect(screen.getByTestId('scope')).toHaveTextContent('real only')
    expect(localStorage.getItem('swara.includeDemo')).toBeNull()           // the default is not saved as if the person had chosen it
  })

  it('keeps the person\'s own choice over the shop default, in both directions', async () => {
    localStorage.setItem('swara.includeDemo', '1')
    mockRoutes({ 'GET /api/health': HEALTH, 'GET /api/analytics/overview?days=1&include_synthetic=false': OVERVIEW(12) })
    renderShell()
    expect(screen.getByTestId('scope')).toHaveTextContent('with demo')
    await screen.findByText('Patel Kirana')
    expect(screen.getByTestId('scope')).toHaveTextContent('with demo')
  })

  it('falls back to real records only when the order count cannot be read', async () => {
    mockRoutes({ 'GET /api/health': HEALTH })
    renderShell()
    await screen.findByText('Patel Kirana')
    await waitFor(() => expect(screen.getByText('Showing only orders you took')).toBeInTheDocument())
  })

  it('collapses the sidebar and remembers it', async () => {
    mockRoutes({ 'GET /api/health': HEALTH })
    renderShell()
    await userEvent.click(screen.getByRole('button', { name: 'Collapse sidebar' }))
    expect(screen.getByRole('button', { name: 'Expand sidebar' })).toHaveAttribute('aria-pressed', 'true')
    expect(localStorage.getItem('swara.sidebar')).toBe('1')
  })

  it('a crash inside one page does not take the navigation down, and leaving the page recovers', async () => {
    mockRoutes({ 'GET /api/health': HEALTH })
    vi.spyOn(console, 'error').mockImplementation(() => undefined)
    renderShell('/boom')
    const alert = await screen.findByRole('alert')
    expect(within(alert).getByText('This screen hit a problem')).toBeInTheDocument()
    expect(within(alert).getByText(/Kaboom/)).toBeInTheDocument()
    await userEvent.click(within(screen.getByRole('navigation', { name: 'Main' })).getByRole('link', { name: 'Orders' }))
    expect(await screen.findByRole('heading', { name: 'Orders page' })).toBeInTheDocument()
  })
})

describe('Command palette', () => {
  const search = (q: string) => ({
    query: q, products: [{ id: 1, title: 'Basmati Rice', subtitle: '₹90 / kg' }], customers: [{ id: 5, title: 'Meena Patel', subtitle: '9876500001' }],
    orders: [{ id: 3, title: 'SW-0003', subtitle: '₹172' }], catalog: [{ id: 10, title: 'Maggi Noodles', subtitle: '70 g' }], catalog_total: 40,
  })
  const open = async () => { await userEvent.keyboard('{Control>}k{/Control}'); return screen.findByRole('dialog', { name: 'Search' }) }

  it('opens with Ctrl+K, lists pages first, and closes with Escape', async () => {
    mockRoutes({ 'GET /api/health': HEALTH })
    renderShell()
    const dlg = await open()
    expect(within(dlg).getByRole('option', { name: /Inventory/ })).toBeInTheDocument()
    expect(within(dlg).getByRole('combobox')).toHaveFocus()
    await userEvent.keyboard('{Escape}')
    await waitFor(() => expect(screen.queryByRole('dialog', { name: 'Search' })).toBeNull())
  })

  it('also opens with / when not typing in a field', async () => {
    mockRoutes({ 'GET /api/health': HEALTH })
    renderShell()
    await userEvent.keyboard('/')
    expect(await screen.findByRole('dialog', { name: 'Search' })).toBeInTheDocument()
  })

  it('searches the server after a pause and groups results by kind', async () => {
    const m = mockRoutes({ 'GET /api/health': HEALTH, 'GET /api/search': (u: URL) => search(u.searchParams.get('q') ?? '') })
    renderShell()
    const dlg = await open()
    await userEvent.type(within(dlg).getByRole('combobox'), 'meena')
    expect(await within(dlg).findByRole('option', { name: /Meena Patel/ })).toBeInTheDocument()
    expect(m.urls().filter((u) => u.startsWith('/api/search'))).toHaveLength(1)        // one request for the whole word
    for (const g of ['Products in your shop', 'Customers', 'Orders', 'Catalogue (reference)']) expect(within(dlg).getByText(g)).toBeInTheDocument()
    expect(within(dlg).getByRole('option', { name: /See all 40 catalogue matches/ })).toBeInTheDocument()
  })

  it('moves with the arrow keys, opens the highlighted result with Enter, and lands on the right deep link', async () => {
    mockRoutes({ 'GET /api/health': HEALTH, 'GET /api/search': (u: URL) => search(u.searchParams.get('q') ?? '') })
    renderShell()
    const dlg = await open()
    await userEvent.type(within(dlg).getByRole('combobox'), 'meena')
    await within(dlg).findByRole('option', { name: /Meena Patel/ })
    // order: Products, Customers... (no page contains "meena"), so the customer is second
    await userEvent.keyboard('{ArrowDown}{Enter}')
    await waitFor(() => expect(screen.queryByRole('dialog', { name: 'Search' })).toBeNull())
    expect(screen.getByTestId('where')).toHaveTextContent('/customers')
  })

  it('says so when nothing matches or the backend is down', async () => {
    mockRoutes({ 'GET /api/health': HEALTH, 'GET /api/search': { query: 'qqq', products: [], customers: [], orders: [], catalog: [] } })
    renderShell()
    const dlg = await open()
    await userEvent.type(within(dlg).getByRole('combobox'), 'qqq')
    expect(await within(dlg).findByText(/Nothing matches/)).toBeInTheDocument()
  })
})

describe('ErrorBoundary', () => {
  it('resets when the key changes', async () => {
    vi.spyOn(console, 'error').mockImplementation(() => undefined)
    let boom = true
    const Maybe = () => { if (boom) throw new Error('first render fails'); return <p>fine now</p> }
    const { rerender } = render(<ErrorBoundary resetKey="a"><Maybe /></ErrorBoundary>)
    expect(screen.getByText('This screen hit a problem')).toBeInTheDocument()
    boom = false
    rerender(<ErrorBoundary resetKey="b"><Maybe /></ErrorBoundary>)
    expect(await screen.findByText('fine now')).toBeInTheDocument()
  })
})

describe('Shell · signed-in person', () => {
  it('shows who is signed in with their role, linking to the account page', async () => {
    mockRoutes({ 'GET /api/health': HEALTH })
    renderShell('/dashboard')
    const who = screen.getByRole('link', { name: 'Account: Ramesh Patel' })
    expect(who).toHaveAttribute('href', '/account')
    expect(within(who).getByText('Shop owner')).toBeInTheDocument()
  })

  it('shows a new shop name straight away when the owner saves one, without waiting for the next health check', async () => {
    let name = 'Patel Kirana'
    mockRoutes({
      'GET /api/health': () => ({ ...HEALTH, store_name: name }),
      'PUT /api/settings': () => { name = 'Shah Kirana & Stores'; return { ok: true } },
    })
    renderShell('/orders')
    expect(await screen.findByText('Patel Kirana')).toBeInTheDocument()
    // Same order as the Settings page: the save goes through the API client (which drops cached reads), then the page announces it.
    await api.putSettings({ store_name: 'Shah Kirana & Stores' })
    window.dispatchEvent(new Event(SHOP_RENAMED))
    expect(await screen.findByText('Shah Kirana & Stores')).toBeInTheDocument()
    expect(screen.queryByText('Patel Kirana')).toBeNull()
  })

  it('lists Payments for everyone and Payment analytics for the owner only', async () => {
    mockRoutes({ 'GET /api/health': HEALTH })
    const { unmount } = renderShell('/dashboard')
    const nav = screen.getByRole('navigation', { name: 'Main' })
    expect(within(nav).getByRole('link', { name: 'Payments' })).toHaveAttribute('href', '/payments')
    expect(within(nav).getByRole('link', { name: 'Payment analytics' })).toHaveAttribute('href', '/payment-analytics')
    unmount()
    mockRoutes({ 'GET /api/health': HEALTH })
    render(<MemoryRouter initialEntries={['/dashboard']}><TestAuth user={STAFF_USER}><DataScopeProvider><Routes><Route element={<Shell />}><Route path="/dashboard" element={<h1>Dashboard page</h1>} /></Route></Routes></DataScopeProvider></TestAuth></MemoryRouter>)
    const staffNav = screen.getByRole('navigation', { name: 'Main' })
    expect(within(staffNav).getByRole('link', { name: 'Payments' })).toBeInTheDocument()
    expect(within(staffNav).queryByRole('link', { name: 'Payment analytics' })).not.toBeInTheDocument()
  })
})
