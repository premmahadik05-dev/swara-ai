import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, describe, expect, it, vi } from 'vitest'
import Performance from './Performance'
import { evaluationSummary, mockRoutes } from '../test/fixtures'
import type { EvaluationResponse } from '../lib/evaluation'
import type { Latency } from '../types'

afterEach(() => { vi.unstubAllGlobals(); localStorage.clear() })

const noLive = (): Latency => ({
  'gnani-stt': { calls: 0, ok: 0, errors: 0, p50_ms: null, p95_ms: null, last_error: null },
  'gnani-tts': { calls: 0, ok: 0, errors: 0, p50_ms: null, p95_ms: null, last_error: null },
  evon: { calls: 0, ok: 0, errors: 0, p50_ms: null, p95_ms: null, last_error: null },
  nlu: { turns: 0, p50_ms: null, p95_ms: null },
})
const response = (over: Partial<EvaluationResponse> = {}): EvaluationResponse => ({
  available: true, summary: evaluationSummary(), file_modified: '2026-11-11T06:00:00+00:00', how_to_create: 'python scripts/build_evaluation_summary.py',
  verification: { generated_at: '2026-11-11T07:00:00+00:00', rows: [
    { category: 'Backend tests', total: 10, passed: 10, failed: 0, skipped: 0, status: 'Passed', how: 'pytest', ran: 'now' },
    { category: 'Live Gnani check', total: null, passed: null, failed: null, skipped: null, status: 'Not run', how: 'needs a key', ran: '' },
  ] }, ...over,
})
const routes = (over: Record<string, unknown> = {}) => ({ 'GET /api/evaluation': response(), 'GET /api/analytics/latency': noLive(), ...over })
const renderIt = () => render(<MemoryRouter><Performance /></MemoryRouter>)
const card = (name: string) => screen.getByRole('heading', { name }).closest('section')!

describe('AI performance page', () => {
  it('leads with the headline figures and their denominators, and says it is text only', async () => {
    mockRoutes(routes())
    renderIt()
    expect(await screen.findByText('Text only: no speech measured')).toBeInTheDocument()
    const kpi = (label: string) => screen.getByRole('group', { name: label })
    expect(within(kpi('Held-out brand match, exact')).getByText('70.0%')).toBeInTheDocument()
    expect(within(kpi('Held-out brand match, exact')).getByText('7 of 10 synthetic sentences')).toBeInTheDocument()
    expect(within(kpi('Wrong product picked')).getByText('10.0%')).toBeInTheDocument()
    expect(within(kpi('Typed orders correct')).getByText('10 of 10')).toBeInTheDocument()
    expect(screen.getByText(/Read these numbers with their limits/)).toBeInTheDocument()
    expect(screen.getByText(/Speech recognition was not measured/)).toBeInTheDocument()
  })

  it('draws the language heatmap with an n/a where a metric does not apply, and the same numbers in its table view', async () => {
    mockRoutes(routes())
    renderIt()
    const c = (await screen.findByRole('heading', { name: 'Language by metric' })).closest('section')!
    const mr = within(c).getByRole('row', { name: /Marathi/ })
    expect(within(mr).getAllByRole('cell').map((x) => x.textContent)).toEqual(['100.0%', 'n/a', '71.4%', 'n/a', '100.0%'])
    await userEvent.click(within(c).getByRole('button', { name: 'Table' }))
    const t = within(c).getByRole('table')
    expect(within(t).getByRole('row', { name: /Marathi/ })).toHaveTextContent('71.4%')
  })

  it('shows both confusion matrices as real tables and lists the wrong products pair by pair', async () => {
    mockRoutes(routes())
    renderIt()
    await screen.findByRole('heading', { name: 'Product category confusion' })
    const cat = screen.getByRole('table', { name: 'Asked-for product category against returned product category' })
    const snacks = within(cat).getByRole('rowheader', { name: 'Snacks' }).closest('tr')!
    expect(within(snacks).getAllByRole('cell').map((c) => c.textContent)).toEqual(['4', '1', '·', '·', '5'])   // 4 right, 1 in another category, nothing asked or missed, 5 sentences
    expect(screen.getByRole('table', { name: 'True language against the language label the parser gave' })).toBeInTheDocument()
    const wrong = card('Wrong products picked, pair by pair')
    expect(within(wrong).getByText('Parle G')).toBeInTheDocument()
    expect(within(wrong).getByText('Parle-G 100 g')).toBeInTheDocument()
  })

  it('offers a table view for every chart', async () => {
    mockRoutes(routes())
    renderIt()
    await screen.findByRole('heading', { name: 'Language by metric' })
    const groups = screen.getAllByRole('group', { name: /: view$/ })
    expect(groups.length).toBeGreaterThanOrEqual(8)
  })

  it('switches the language evaluation table between sentence sets', async () => {
    mockRoutes(routes())
    renderIt()
    const c = (await screen.findByRole('heading', { name: 'Language evaluation' })).closest('section')!
    expect(within(c).getByRole('row', { name: /Marathi/ })).toBeInTheDocument()
    await userEvent.click(within(c).getByRole('button', { name: 'Held-out branded products' }))
    expect(within(c).queryByRole('row', { name: /Marathi/ })).toBeNull()   // no held-out sentences for Marathi: left out, not shown as 0%
    const hi = within(c).getByRole('row', { name: /Hindi/ })
    expect(within(hi).getAllByRole('cell').map((x) => x.textContent)).toEqual(['Hindi', '5', '3', '0', '1', '1', '60.0%'])
  })

  it('lists speech timings as not measured until a live call exists, and never estimates them', async () => {
    mockRoutes(routes())
    renderIt()
    const c = (await screen.findByRole('heading', { name: 'AI evaluation metrics' })).closest('section')!
    await userEvent.type(within(c).getByRole('searchbox'), 'Speech recognition')
    const row = within(c).getByRole('row', { name: /Speech recognition time/ })
    expect(within(row).getByText('Not measured')).toBeInTheDocument()
    expect(screen.getByText('No live call recorded')).toBeInTheDocument()
  })

  it('shows measured speech timings, marked live, once calls exist', async () => {
    const lat = noLive()
    lat['gnani-stt'] = { calls: 4, ok: 4, errors: 0, p50_ms: 640, p95_ms: 910, last_error: null }
    mockRoutes(routes({ 'GET /api/analytics/latency': lat }))
    renderIt()
    const c = (await screen.findByRole('heading', { name: 'AI evaluation metrics' })).closest('section')!
    await userEvent.type(within(c).getByRole('searchbox'), 'Speech recognition')
    await waitFor(() => expect(within(c).getByText(/p50 640 ms, p95 910 ms \(4 calls\)/)).toBeInTheDocument())
    expect(within(c).getByText('Live')).toBeInTheDocument()
  })

  it('shows the test record and the technology stack with their statuses', async () => {
    mockRoutes(routes())
    renderIt()
    const t = (await screen.findByRole('heading', { name: 'Test and verification' })).closest('section')!
    expect(within(within(t).getByRole('row', { name: /Backend tests/ })).getByText('Passed')).toBeInTheDocument()
    expect(within(within(t).getByRole('row', { name: /Live Gnani check/ })).getByText('Not run')).toBeInTheDocument()
    const g = card('Technology stack')
    // what was not verified live is amber, never the green of "implemented and tested"
    expect(within(within(g).getByRole('row', { name: /Speech recognition/ })).getByText(/not live-verified/)).toHaveClass('warn')
    expect(within(within(g).getByRole('row', { name: /API server/ })).getByText('Implemented and tested')).toHaveClass('ok')
    expect(within(within(t).getByRole('row', { name: /Live Gnani check/ })).getByText('Not run')).toHaveClass('warn')
    expect(within(within(t).getByRole('row', { name: /Backend tests/ })).getByText('Passed')).toHaveClass('ok')
  })

  it('says how to build the results when the file is missing, and draws nothing in the meantime', async () => {
    mockRoutes(routes({ 'GET /api/evaluation': { available: false, summary: null, how_to_create: 'python scripts/build_evaluation_summary.py' } }))
    renderIt()
    expect(await screen.findByText('The evaluation results have not been built yet')).toBeInTheDocument()
    expect(screen.getByText('python scripts/build_evaluation_summary.py')).toBeInTheDocument()
    expect(screen.queryByRole('heading', { name: 'Language by metric' })).toBeNull()
  })

  it('says there is no test record yet instead of inventing one', async () => {
    mockRoutes(routes({ 'GET /api/evaluation': response({ verification: null }) }))
    renderIt()
    expect(await screen.findByText('No test record yet')).toBeInTheDocument()
  })

  it('shows measured server response times only when the benchmark file exists, and says what they are not', async () => {
    const stat = (p50: number) => ({ n: 100, p50_ms: p50, p95_ms: p50 * 1.5, max_ms: p50 * 3, mean_ms: p50 })
    mockRoutes(routes({ 'GET /api/evaluation': response({ api_latency: { machine: 'Test machine', note: 'Local loopback HTTP.', n: 200, text_turn: stat(7), confirm_order_with_stock_update: stat(11) } }) }))
    renderIt()
    const c = within((await screen.findByRole('heading', { name: 'Server response time' })).closest('section')!)
    expect(c.getByRole('row', { name: /Order desk, one turn 7 10.5 100/ })).toBeInTheDocument()
    expect(c.getByText(/not what a shop on a real network will see/)).toBeInTheDocument()
    expect(c.getByText(/contains no Gnani call/)).toBeInTheDocument()
  })

  it('omits the server response time card when there is no benchmark file', async () => {
    mockRoutes(routes({ 'GET /api/evaluation': response({ api_latency: null }) }))
    renderIt()
    await screen.findByText('Text only: no speech measured')
    expect(screen.queryByRole('heading', { name: 'Server response time' })).toBeNull()
  })
})
