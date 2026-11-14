import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, describe, expect, it, vi } from 'vitest'
import OrderDesk from './OrderDesk'
import { TestAuth } from '../test/auth'
import { ToastProvider } from '../components/Toast'
import { json, languageInfo, languages, turn } from '../test/fixtures'
import { LANG_META } from '../lib/languages'

afterEach(() => vi.unstubAllGlobals())

const HEALTH = { status: 'ok', db: 'ok', products: 65, gnani_configured: false, version: '1', store_name: 'Demo' }

function mockServer(handlers: Record<string, (body: unknown) => Response>) {
  const calls: { key: string; body: unknown }[] = []
  vi.stubGlobal('fetch', vi.fn().mockImplementation(async (url: string, init: RequestInit = {}) => {
    const key = `${init.method ?? 'GET'} ${url}`
    const body = typeof init.body === 'string' ? JSON.parse(init.body) : null
    calls.push({ key, body })
    if (key === 'GET /api/health') return json(HEALTH)
    if (key === 'GET /api/languages') return json(languages())
    const h = handlers[key]
    if (!h) throw new Error(`unmocked ${key}`)
    return h(body)
  }))
  return calls
}
const renderIt = () => render(<MemoryRouter><TestAuth><ToastProvider><OrderDesk /></ToastProvider></TestAuth></MemoryRouter>)

describe('OrderDesk (text channel)', () => {
  it('explains that the mic needs a key but typing works, and disables the mic', async () => {
    mockServer({})
    renderIt()
    expect(await screen.findByText(/Typing works now/)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /Add a Gnani key to use the microphone/ })).toBeDisabled()
  })

  it('sends a typed sentence, shows both bubbles and the bill, reusing the session on the next turn', async () => {
    const calls = mockServer({ 'POST /api/text/turn': () => json(turn({ transcript: 'mane 2 kilo chawal joie' })) })
    renderIt()
    await screen.findByText(/Typing works now/)
    const box = screen.getByLabelText('Or type the order')
    await userEvent.type(box, 'mane 2 kilo chawal joie')
    await userEvent.click(screen.getByRole('button', { name: 'Send' }))
    expect(await screen.findByText('2 kilo Rice add kar diya.')).toBeInTheDocument()
    expect(screen.getByText('mane 2 kilo chawal joie')).toBeInTheDocument()
    expect(screen.getByText('₹172')).toBeInTheDocument()
    expect(calls.find((c) => c.key === 'POST /api/text/turn')!.body).toEqual({ text: 'mane 2 kilo chawal joie', speak: false, language: 'gu' })

    await userEvent.type(box, 'ek litre doodh')
    await userEvent.click(screen.getByRole('button', { name: 'Send' }))
    await waitFor(() => expect(calls.filter((c) => c.key === 'POST /api/text/turn')).toHaveLength(2))
    expect(calls.filter((c) => c.key === 'POST /api/text/turn')[1].body).toMatchObject({ session_id: 's1' })
  })

  it('blocks Confirm while the assistant is waiting for an answer, then confirms and shows the saved order', async () => {
    let step = 0
    const calls = mockServer({
      'POST /api/text/turn': () => json(++step === 1
        ? turn({ pending: { kind: 'choose_product', product: 'dal', options: [{ id: 1, name: 'Toor Dal' }, { id: 2, name: 'Moong Dal' }], remaining: 0 }, awaiting: 'choose_product' })
        : turn({ phase: 'confirming', awaiting: 'confirm_order', pending: null })),
      'POST /api/sessions/s1/confirm': () => json(turn({
        phase: 'completed', awaiting: null, reply_text: 'Order SW-1 ho gaya.',
        order: { id: 1, code: 'SW-1', status: 'confirmed', channel: 'text', language: 'hinglish', customer_id: null, customer_name: '', total_paise: 17200, is_synthetic: false, created_at: '2026-11-10T05:00:00Z', session_id: 's1', items: [] },
      })),
    })
    renderIt()
    await screen.findByText(/Typing works now/)
    await userEvent.type(screen.getByLabelText('Or type the order'), 'dal chahiye')
    await userEvent.click(screen.getByRole('button', { name: 'Send' }))
    expect(await screen.findByText('Which dal?')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Confirm order' })).toBeDisabled()

    await userEvent.click(screen.getByRole('button', { name: 'Moong Dal' }))
    await waitFor(() => expect(screen.getByRole('button', { name: 'Confirm order' })).toBeEnabled())
    await userEvent.click(screen.getByRole('button', { name: 'Confirm order' }))
    expect(await screen.findByRole('region', { name: 'Order confirmed' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Take payment' })).toBeInTheDocument()   // payment is offered, never forced: Next customer still works
    expect(screen.getByRole('button', { name: 'Next customer' })).toBeEnabled()
    expect(screen.getAllByText(/SW-1/).length).toBeGreaterThan(0)
    expect(calls.some((c) => c.key === 'POST /api/sessions/s1/confirm')).toBe(true)
  })

  it('shows the server message when a turn fails', async () => {
    mockServer({ 'POST /api/text/turn': () => json({ detail: { code: 'RATE_LIMITED', message: 'Slow down a little.' } }, 429) })
    renderIt()
    await screen.findByText(/Typing works now/)
    await userEvent.type(screen.getByLabelText('Or type the order'), 'chawal')
    await userEvent.click(screen.getByRole('button', { name: 'Send' }))
    expect((await screen.findAllByText('Slow down a little.')).length).toBeGreaterThan(0)
  })
})


describe('OrderDesk: language selection', () => {
  it('starts in Gujarati, lists all eleven languages, and sends the chosen one with a typed turn', async () => {
    const calls = mockServer({ 'POST /api/text/turn': () => json(turn({ language: 'ta' })) })
    renderIt()
    await screen.findByText(/Typing works now/)
    const trigger = screen.getByRole('button', { name: /Customer speaks/ })
    expect(trigger).toHaveTextContent('ગુજરાતી')
    await userEvent.click(trigger)
    expect(within(screen.getByRole('radiogroup', { name: 'Languages' })).getAllByRole('radio')).toHaveLength(12)
    await userEvent.click(screen.getByRole('radio', { name: /தமிழ்/ }))
    expect(screen.getByRole('button', { name: /Customer speaks/ })).toHaveTextContent('தமிழ்')
    await userEvent.type(screen.getByLabelText('Or type the order'), 'இரண்டு கிலோ அரிசி')
    await userEvent.click(screen.getByRole('button', { name: 'Send' }))
    await waitFor(() => expect(calls.some((c) => c.key === 'POST /api/text/turn')).toBe(true))
    expect(calls.find((c) => c.key === 'POST /api/text/turn')!.body).toMatchObject({ text: 'இரண்டு கிலோ அரிசி', language: 'ta' })
  })

  it('offers example sentences in the chosen language, from the server list', async () => {
    mockServer({})
    renderIt()
    await screen.findByText(/Typing works now/)
    await userEvent.click(screen.getByRole('button', { name: /Customer speaks/ }))
    await userEvent.click(screen.getByRole('radio', { name: /বাংলা/ }))
    expect(await screen.findByRole('button', { name: languageInfo('bn').sample })).toBeInTheDocument()
  })

  it('moves to the first language that is on when the server says the saved one has been switched off', async () => {
    const rows = languages().languages.map((l) => l.key === 'gu' ? { ...l, enabled: false } : l)
    vi.stubGlobal('fetch', vi.fn().mockImplementation(async (url: string) => {
      if (url === '/api/health') return json(HEALTH)
      if (url === '/api/languages') return json(languages({ disabled: ['gu'] }, rows))
      throw new Error(`unmocked ${url}`)
    }))
    renderIt()
    await screen.findByText(/Typing works now/)
    await waitFor(() => expect(screen.getByRole('button', { name: /Customer speaks/ })).toHaveTextContent('हिन्दी'))
  })

  it('says Auto-detect is unavailable on this server and does not select it', async () => {
    mockServer({})
    renderIt()
    await screen.findByText(/Typing works now/)
    await userEvent.click(screen.getByRole('button', { name: /Customer speaks/ }))
    expect(screen.getByRole('radio', { name: /Auto-detect/ })).toBeDisabled()
  })

  it('refreshes the list and shows the server\'s reason when a language is refused', async () => {
    let listCalls = 0
    vi.stubGlobal('fetch', vi.fn().mockImplementation(async (url: string, init: RequestInit = {}) => {
      if (url === '/api/health') return json(HEALTH)
      if (url === '/api/languages') { listCalls++; return json(languages()) }
      if (url === '/api/text/turn' && init.method === 'POST') return json({ detail: { code: 'LANGUAGE_DISABLED', message: 'Marathi is switched off on this server.' } }, 422)
      throw new Error(`unmocked ${url}`)
    }))
    renderIt()
    await screen.findByText(/Typing works now/)
    await userEvent.type(screen.getByLabelText('Or type the order'), 'दोन किलो साखर')
    await userEvent.click(screen.getByRole('button', { name: 'Send' }))
    expect((await screen.findAllByText('Marathi is switched off on this server.')).length).toBeGreaterThan(0)
    await waitFor(() => expect(listCalls).toBeGreaterThanOrEqual(2))
  })

  it('still lets the person pick any language when the language list cannot be loaded, without showing any status', async () => {
    vi.stubGlobal('fetch', vi.fn().mockImplementation(async (url: string) => {
      if (url === '/api/health') return json(HEALTH)
      throw new Error('offline')
    }))
    renderIt()
    await screen.findByText(/Typing works now/)
    await userEvent.click(screen.getByRole('button', { name: /Customer speaks/ }))
    expect(screen.getAllByRole('radio')).toHaveLength(LANG_META.length + 1)
    expect(screen.queryByText('Live checked')).toBeNull()
  })
})
