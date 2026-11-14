import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, describe, expect, it, vi } from 'vitest'
import Dashboard from './Dashboard'
import { STAFF_USER, TestAuth } from '../test/auth'
import { DataScopeProvider } from '../lib/scope'
import { demand, inventorySummary, mockRoutes, order, orderList, overview, salesSeries } from '../test/fixtures'

afterEach(() => { vi.unstubAllGlobals(); localStorage.clear() })
const routes = (over: Record<string, unknown> = {}) => ({
  'GET /api/analytics/sales': (u: URL) => salesSeries(u.searchParams.get('grain') as 'day' | 'week' | 'month', Number(u.searchParams.get('periods')), { cur: 120000, prev: 100000, window: 7 }),
  'GET /api/analytics/overview': overview(), 'GET /api/analytics/demand': demand(), 'GET /api/analytics/inventory': inventorySummary(),
  'GET /api/orders': orderList([order(), order({ id: 2, code: 'SW-0002', is_synthetic: true })]),
  'GET /api/health': { status: 'ok', db: 'ok', products: 70, gnani_configured: false, version: '2', store_name: 'Patel Kirana & General Store (demo)', store_name_is_default: true }, ...over,
})
const renderIt = (user = undefined as typeof STAFF_USER | undefined) => render(<MemoryRouter><TestAuth {...(user ? { user } : {})}><DataScopeProvider><Dashboard /></DataScopeProvider></TestAuth></MemoryRouter>)

describe('Dashboard', () => {
  it('computes the 7-day tiles from the daily series, leaving today out, with the change against the 7 days before', async () => {
    mockRoutes(routes())
    renderIt()
    // seven complete days at ₹1,200 = ₹8,400, against seven at ₹1,000
    expect(await screen.findByText('₹8,400')).toBeInTheDocument()
    expect(screen.getAllByText(/\+20(\.0)?%/).length).toBeGreaterThan(0)
    expect(screen.getByText('70')).toBeInTheDocument()                       // 7 days x 10 orders
    expect(screen.getAllByText(/Today so far/).length).toBeGreaterThan(0)    // the unfinished day is shown separately
  })

  it('says the data is generated whenever demo data is on, and drops the warning when it is off', async () => {
    localStorage.setItem('swara.includeDemo', '1')   // these tests are about the demo-on state; the default for a shop is decided by its data (see shell.test)
    mockRoutes(routes())
    const { unmount } = renderIt()
    expect(await screen.findByText('Includes generated demo data')).toBeInTheDocument()
    expect(screen.getByText(/They are not real sales/)).toBeInTheDocument()
    unmount()
    localStorage.setItem('swara.includeDemo', '0')
    const m = mockRoutes(routes())
    renderIt()
    expect(await screen.findByText('Only orders you recorded')).toBeInTheDocument()
    expect(screen.queryByText(/They are not real sales/)).toBeNull()
    await waitFor(() => expect(m.urls().filter((u) => u.includes('include_synthetic=false')).length).toBeGreaterThanOrEqual(4))
  })

  it('lists what needs restocking from the database, and the items that will run out soonest', async () => {
    mockRoutes(routes())
    renderIt()
    const card = (await screen.findByRole('heading', { name: 'Restock now' })).closest('section') as HTMLElement
    expect(within(card).getByText('Toor Dal')).toBeInTheDocument()
    expect(within(card).getByText('Finished')).toBeInTheDocument()
    expect(within(card).getByText('3 kg left')).toBeInTheDocument()
    expect(within(card).getByText('1 days of stock')).toBeInTheDocument()
  })

  it('switches the trend grouping and asks the server for that grouping', async () => {
    const m = mockRoutes(routes())
    renderIt()
    await screen.findByText('₹8,400')
    await userEvent.click(screen.getByRole('button', { name: 'Weekly' }))
    await waitFor(() => expect(m.urls().some((u) => u.includes('grain=week'))).toBe(true))
  })

  it('shows a welcoming empty state, not a blank chart, when there are no orders', async () => {
    const none = (u: URL) => { const s = salesSeries('day', Number(u.searchParams.get('periods'))); return { ...s, series: s.series.map((p) => ({ ...p, revenue_paise: 0, orders: 0, avg_basket_paise: 0 })), totals: { revenue_paise: 0, orders: 0, avg_basket_paise: 0 } } }
    mockRoutes(routes({ 'GET /api/analytics/sales': none, 'GET /api/orders': orderList([], 0) }))
    renderIt()
    expect(await screen.findByText('No orders in this period')).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Take the first order' })).toHaveAttribute('href', '/order')
  })

  it('shows skeletons while loading', () => {
    vi.stubGlobal('fetch', vi.fn().mockImplementation(() => new Promise(() => undefined)))
    renderIt()
    expect(screen.getAllByRole('status', { name: 'Loading' }).length).toBeGreaterThan(2)
  })

  it('shows one retryable error when the backend is unreachable', async () => {
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new TypeError('x')))
    renderIt()
    expect(await screen.findByText(/Cannot reach the SWARA AI server/)).toBeInTheDocument()
    expect(screen.getAllByRole('button', { name: 'Try again' })).toHaveLength(1)
  })

  describe('welcome strip', () => {
    it('greets the person by first name and offers the two things an owner does most', async () => {
      mockRoutes(routes())
      renderIt()
      expect(await screen.findByRole('heading', { level: 2, name: /^Good (morning|afternoon|evening), Ramesh$/ })).toBeInTheDocument()
      expect(screen.getByRole('heading', { level: 1, name: 'Dashboard' })).toBeInTheDocument()
      expect(screen.getByRole('link', { name: 'Take an order' })).toHaveAttribute('href', '/order')
      expect(screen.getByRole('link', { name: 'Manage stock' })).toHaveAttribute('href', '/inventory')
    })

    it('does not send staff to stock management, which they cannot change', async () => {
      mockRoutes(routes())
      renderIt(STAFF_USER)
      expect(await screen.findByRole('heading', { level: 2, name: /Meena$/ })).toBeInTheDocument()
      expect(screen.getByRole('link', { name: 'Take an order' })).toBeInTheDocument()
      expect(screen.queryByRole('link', { name: 'Manage stock' })).toBeNull()
    })

    it('shows the owner a setup checklist built from real figures: demo prices, orders on record, the shop name', async () => {
      mockRoutes(routes())
      renderIt()
      const card = await screen.findByRole('region', { name: 'Set up your shop' })
      expect(within(card).getByText(/1 of 4 done/)).toBeInTheDocument()                    // fixtures: 5 prices set by the shop, no real orders yet
      expect(within(card).getByText(/65 of 70 items still carry a placeholder demo price/)).toBeInTheDocument()
      expect(within(card).getByRole('link', { name: 'Open order desk' })).toHaveAttribute('href', '/order')
    })

    it('does not show staff the checklist, and does not even ask the server the questions behind it', async () => {
      const m = mockRoutes(routes())
      renderIt(STAFF_USER)
      await screen.findByRole('heading', { level: 2, name: /Meena$/ })
      await waitFor(() => expect(m.urls().some((u) => u.startsWith('/api/analytics/inventory'))).toBe(true))
      expect(screen.queryByRole('region', { name: 'Set up your shop' })).toBeNull()
      expect(m.urls()).not.toContain('/api/health')
    })
  })
})
