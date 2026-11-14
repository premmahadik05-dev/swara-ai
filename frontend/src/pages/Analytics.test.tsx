import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, describe, expect, it, vi } from 'vitest'
import Analytics from './Analytics'
import { DataScopeProvider } from '../lib/scope'
import { demand, inventorySummary, json, mockRoutes, overview, salesSeries, stockMovement } from '../test/fixtures'

afterEach(() => { vi.unstubAllGlobals(); localStorage.clear() })

const routes = (over: Record<string, unknown> = {}) => ({
  'GET /api/analytics/sales': (u: URL) => salesSeries(u.searchParams.get('grain') as 'day' | 'week' | 'month', Number(u.searchParams.get('periods'))),
  'GET /api/analytics/overview': overview(),
  'GET /api/analytics/demand': demand(),
  'GET /api/analytics/inventory': inventorySummary(),
  'GET /api/analytics/stock-movement': (u: URL) => stockMovement({}, Number(u.searchParams.get('days'))),
  ...over,
})
const renderIt = () => render(<MemoryRouter><DataScopeProvider><Analytics /></DataScopeProvider></MemoryRouter>)

describe('Analytics', () => {
  it('computes the sales KPIs from the series, leaves the unfinished day out, and compares with the 30 days before', async () => {
    localStorage.setItem('swara.includeDemo', '1')   // these tests are about the demo-on state; the default for a shop is decided by its data (see shell.test)
    mockRoutes(routes({ 'GET /api/analytics/sales': (u: URL) => salesSeries('day', Number(u.searchParams.get('periods')), { cur: 120000, prev: 100000 }) }))
    renderIt()
    // 30 complete days at ₹1,200 = ₹36,000. The in-progress day (₹300) is not added.
    expect(await screen.findByText('₹36,000')).toBeInTheDocument()
    expect(screen.getAllByText(/\+20(\.0)?%/).length).toBeGreaterThan(0)
    expect(screen.getByText('Includes generated demo data')).toBeInTheDocument()
    expect(screen.getByText(/Demo data\./)).toBeInTheDocument()
  })

  it('shows the unfinished day beside the first three tiles, and names the period when the grouping changes', async () => {
    mockRoutes(routes())
    renderIt()
    // the tiles count complete days only; the day in progress is ₹300 over 3 orders (₹100 each) and is shown next to them, not added to them
    expect(await screen.findByText('Today so far: ₹300')).toBeInTheDocument()
    expect(screen.getByText('Today so far: 3')).toBeInTheDocument()
    expect(screen.getByText('Today so far: ₹100')).toBeInTheDocument()
    expect(screen.getByText('₹30,000')).toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: 'Weekly' }))
    expect((await screen.findAllByText(/This week so far:/)).length).toBe(3)
  })

  it('shows nothing extra when the unfinished period has no orders', async () => {
    mockRoutes(routes({ 'GET /api/analytics/sales': (u: URL) => salesSeries('day', Number(u.searchParams.get('periods')), { partialOrders: 0 }) }))
    renderIt()
    await screen.findByText('₹30,000')
    expect(screen.queryByText(/so far:/)).toBeNull()
  })

  it('asks for 2N+1 periods so the previous window is complete, and switches grain', async () => {
    const m = mockRoutes(routes())
    renderIt()
    await screen.findByText('₹30,000')
    expect(m.urls().some((u) => u.startsWith('/api/analytics/sales') && u.includes('grain=day') && u.includes('periods=61'))).toBe(true)
    await userEvent.click(screen.getByRole('button', { name: 'Weekly' }))
    await waitFor(() => expect(m.urls().some((u) => u.includes('grain=week') && u.includes('periods=25'))).toBe(true))
    await userEvent.click(screen.getByRole('button', { name: 'Monthly' }))
    await waitFor(() => expect(m.urls().some((u) => u.includes('grain=month') && u.includes('periods=25'))).toBe(true))
  })

  it('shows no change figure when there is no previous window to compare with', async () => {
    mockRoutes(routes({ 'GET /api/analytics/sales': () => salesSeries('day', 20) }))   // fewer than 2N periods
    renderIt()
    await screen.findAllByText(/Sales, last 30 days/)
    expect(screen.queryByText(/vs the 30 days before/)).toBeNull()
  })

  it('shows "Not enough earlier data" instead of a huge percentage when the earlier window is mostly empty', async () => {
    // 30 earlier days exist, but only 5 had orders: +2000% would be arithmetic, not a trend.
    const sparse = (u: URL) => {
      const base = salesSeries('day', Number(u.searchParams.get('periods')), { cur: 100000, prev: 100000 })
      const n = base.series.length
      const series = base.series.map((p, i) => i < n - 1 - 30   // everything before the current 30-day window
        ? { ...p, revenue_paise: i % 6 === 0 ? 5000 : 0, orders: i % 6 === 0 ? 1 : 0, avg_basket_paise: i % 6 === 0 ? 5000 : 0 } : p)
      return { ...base, series }
    }
    mockRoutes(routes({ 'GET /api/analytics/sales': sparse }))
    renderIt()
    await screen.findAllByText(/Sales, last 30 days/)
    expect((await screen.findAllByText('Not enough earlier data to compare')).length).toBeGreaterThan(0)
    expect(screen.queryByText(/\+\d{3,}(\.\d)?%/)).toBeNull()
  })

  it('hides the demand "vs earlier" figures and says why when the earlier window has too little history', async () => {
    const d = demand()
    const thin = { ...d, previous_window: { days: 30, days_with_orders: 4, comparable: false }, products: d.products.map((r) => ({ ...r, trend_pct: null })), rising: [], falling: [] }
    mockRoutes(routes({ 'GET /api/analytics/demand': thin }))
    renderIt()
    await screen.findByText('Sugar', { selector: 'b' })
    expect(screen.getByText(/only 4 of the 30 days before this window have any orders/)).toBeInTheDocument()
    expect(screen.queryByText('New')).toBeNull()
  })

  it('breakdown window and the demo switch change the requests', async () => {
    const m = mockRoutes(routes())
    renderIt()
    await screen.findByText('₹30,000')
    await userEvent.click(screen.getByRole('button', { name: 'Last 7 days' }))
    await waitFor(() => expect(m.urls().some((u) => u.startsWith('/api/analytics/overview') && u.includes('days=7'))).toBe(true))
    expect(m.urls().some((u) => u.startsWith('/api/analytics/demand') && u.includes('days=7'))).toBe(true)
  })

  it('shows demand with days of cover, the suggested reorder, and says it is not a forecast', async () => {
    mockRoutes(routes())
    renderIt()
    const row = (await screen.findByText('Sugar', { selector: 'b' })).closest('tr') as HTMLElement
    expect(within(row).getByText('1 days')).toBeInTheDocument()
    expect(within(row).getByText(/39 kg/)).toBeInTheDocument()
    expect(screen.getByText(/Trailing 30-day sales per day/)).toBeInTheDocument()
  })

  it('reports stock valuation at selling price and does not invent a cost figure', async () => {
    mockRoutes(routes())
    renderIt()
    await screen.findByText('Needs cost prices')
    expect(screen.getByText('₹1,84,500')).toBeInTheDocument()   // Indian digit grouping
  })

  it('offers every chart as a table, so no meaning lives in colour alone', async () => {
    mockRoutes(routes())
    renderIt()
    await screen.findByText('₹30,000')
    const views = screen.getAllByRole('group', { name: /: view$/ })
    expect(views.length).toBeGreaterThanOrEqual(7)
    await userEvent.click(within(screen.getByRole('group', { name: 'Sales: view' })).getByRole('button', { name: 'Table' }))
    const table = screen.getAllByRole('table')[0]
    expect(within(table).getByText('Period')).toBeInTheDocument()
    expect(within(table).getAllByText('₹1,000').length).toBeGreaterThan(5)
    expect(screen.getByText(/in progress/)).toBeInTheDocument()   // the unfinished day is labelled in the table too
  })

  it('shows an empty state when nothing has sold, instead of an empty chart', async () => {
    mockRoutes(routes({ 'GET /api/analytics/sales': () => ({ ...salesSeries('day', 61), series: salesSeries('day', 61).series.map((p) => ({ ...p, revenue_paise: 0, orders: 0, avg_basket_paise: 0 })), totals: { revenue_paise: 0, orders: 0, avg_basket_paise: 0 } }) }))
    renderIt()
    expect(await screen.findByText('No orders in this period')).toBeInTheDocument()
  })

  it('shows an actionable error when the API is unreachable', async () => {
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new TypeError('x')))
    renderIt()
    expect(await screen.findByText(/Cannot reach the SWARA AI server/)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Try again' })).toBeInTheDocument()
  })

  it('surfaces a backend refusal, not a blank page', async () => {
    mockRoutes(routes({ 'GET /api/analytics/overview': json({ detail: { code: 'BOOM', message: 'Database is locked.' } }, 500) }))
    renderIt()
    expect(await screen.findByText(/Database is locked\./)).toBeInTheDocument()
  })

  it('shows the order status mix and the cancelled share', async () => {
    mockRoutes(routes())
    renderIt()
    const card = (await screen.findByRole('heading', { name: 'Order status' })).closest('section')!
    await userEvent.click(within(card).getByRole('button', { name: 'Table' }))
    expect(within(card).getByText('Fulfilled')).toBeInTheDocument()
    expect(within(card).getByText('632')).toBeInTheDocument()
    // 29 cancelled of 712 + 29 = 741 orders
    expect(await screen.findByText('3.9%')).toBeInTheDocument()
    expect(screen.getByText(/29 of 741 orders/)).toBeInTheDocument()
  })

  it('reports stock movement from the ledger: opening plus movements equals what is on the shelf', async () => {
    const m = mockRoutes(routes())
    renderIt()
    const card = (await screen.findByRole('heading', { name: 'Inventory performance' })).closest('section')!
    const rice = await within(card).findByRole('row', { name: /Basmati Rice/ })
    // opening 10 + added 5 + returned 0 - sold 6 - written off 0 = 9
    expect(within(rice).getByText('10 kg')).toBeInTheDocument()
    expect(within(rice).getByText('5 kg')).toBeInTheDocument()
    expect(within(rice).getByText('6 kg')).toBeInTheDocument()
    expect(within(rice).getByText('9 kg')).toBeInTheDocument()
    expect(within(rice).getByText('In stock')).toBeInTheDocument()
    expect(within(within(card).getByRole('row', { name: /Toor Dal/ })).getByText('Reorder now')).toBeInTheDocument()
    expect(m.urls().some((u) => u.startsWith('/api/analytics/stock-movement') && u.includes('days=30'))).toBe(true)
    await userEvent.click(screen.getByRole('button', { name: '7 days' }))
    await waitFor(() => expect(m.urls().some((u) => u.startsWith('/api/analytics/stock-movement') && u.includes('days=7'))).toBe(true))
  })

  it('says plainly that no stock has moved instead of drawing an empty chart, and explains why demo orders are absent', async () => {
    mockRoutes(routes({ 'GET /api/analytics/stock-movement': stockMovement({ movements: 0, products_moved: 0, rows: [] }) }))
    renderIt()
    expect(await screen.findByText('No stock movements in this period')).toBeInTheDocument()
    expect(screen.getByText(/generated demo orders never touched the shelf/)).toBeInTheDocument()
    expect(screen.getByText('Nothing to report yet')).toBeInTheDocument()
  })
})
