import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, describe, expect, it, vi } from 'vitest'
import Live from './Live'
import { RICE, mockRoutes, turn } from '../test/fixtures'
import type { SessionSnapshot, SessionTurn } from '../types'

afterEach(() => vi.unstubAllGlobals())

const t = (over: Partial<SessionTurn>): SessionTurn => ({ id: 1, role: 'customer', text: 'do kilo chawal', language: 'hinglish', input_mode: 'voice', stt_ms: 820, nlu_ms: 1.2, tts_ms: null, audio_id: null, detail: {}, created_at: '2026-11-10T05:00:00Z', ...over })
const snapshot = (): SessionSnapshot => ({
  session_id: 's1', phase: 'collecting', awaiting: 'more_items', language: 'hinglish', created_at: 'x', updated_at: 'x', pending: null,
  cart: { lines: [RICE], total_paise: 11600 },
  turns: [
    t({ detail: { parse: turn().parse } }),
    t({ id: 2, role: 'assistant', text: '2 kilo Rice add kar diya.', input_mode: 'text', stt_ms: null, nlu_ms: null, tts_ms: 410, audio_id: 'a1', detail: { events: [{ type: 'item_added' }] } }),
  ],
})
const latency = {
  'gnani-stt': { calls: 0, errors: 0, p50_ms: null, p95_ms: null }, 'gnani-tts': { calls: 3, errors: 1, p50_ms: 400, p95_ms: 900 },
  evon: { calls: 0, errors: 0, p50_ms: null, p95_ms: null }, nlu: { turns: 12, p50_ms: 1, p95_ms: 3 },
}
const routes = (over: Record<string, unknown> = {}) => ({
  'GET /api/sessions': [{ session_id: 's1', phase: 'collecting', language: 'hinglish', turns: 2 }, { session_id: 's2', phase: 'completed', language: 'gu', turns: 5 }],
  'GET /api/sessions/s1': snapshot(), 'GET /api/analytics/latency': latency, ...over,
})

describe('Conversations', () => {
  it('opens the newest conversation and shows what was heard, how it was understood and how long each step took', async () => {
    mockRoutes(routes())
    render(<MemoryRouter><Live /></MemoryRouter>)
    expect(await screen.findByText('"do kilo chawal"')).toBeInTheDocument()
    expect(screen.getByText('2 kilo Rice add kar diya.')).toBeInTheDocument()
    expect(screen.getByRole('img', { name: /Speech to text 820 ms/ })).toBeInTheDocument()
    const bill = screen.getByRole('region', { name: 'Bill so far' })
    expect(within(bill).getByText('₹116', { selector: '.big' })).toBeInTheDocument()
    expect(within(bill).queryByRole('button')).toBeNull()                    // read-only: editing happens on the Order desk
    expect(screen.getByLabelText('Assistant reply audio')).toHaveAttribute('src', '/api/audio/a1')
  })

  it('reports model calls as measured, with a zero-call row shown as zero rather than invented latency', async () => {
    mockRoutes(routes())
    render(<MemoryRouter><Live /></MemoryRouter>)
    const row = (await screen.findByText('Speech to text')).closest('tr') as HTMLElement
    expect(within(row).getAllByText('0').length).toBeGreaterThan(0)
    expect(screen.getByText(/Evon is not called/)).toBeInTheDocument()
  })

  it('switches conversation when another one is chosen', async () => {
    const m = mockRoutes(routes({ 'GET /api/sessions/s2': { ...snapshot(), session_id: 's2', turns: [t({ id: 9, text: 'ek litre doodh', language: 'gu' })] } }))
    render(<MemoryRouter><Live /></MemoryRouter>)
    await screen.findByText('"do kilo chawal"')
    await userEvent.click(screen.getByRole('button', { name: /Gujarati\s*5 turns/ }))
    expect(await screen.findByText('"ek litre doodh"')).toBeInTheDocument()
    expect(m.urls()).toContain('/api/sessions/s2')
  })

  it('tells a new user what to do when there are no conversations', async () => {
    mockRoutes(routes({ 'GET /api/sessions': [] }))
    render(<MemoryRouter><Live /></MemoryRouter>)
    expect(await screen.findByText('No conversations yet')).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Open the Order desk' })).toHaveAttribute('href', '/order')
  })
})
