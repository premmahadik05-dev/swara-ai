import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import OrderDesk from './OrderDesk'
import { TestAuth } from '../test/auth'
import { ToastProvider } from '../components/Toast'
import { json, languages, turn } from '../test/fixtures'
import { saveOpenSession } from '../lib/openSession'

// A microphone is not available in jsdom: stand in for the recorder and hand back a short, audible recording.
vi.mock('../lib/audio', async (orig) => {
  const real = await orig<typeof import('../lib/audio')>()
  class FakeRecorder {
    endedAt = null
    start() { return Promise.resolve() }
    stop() { return Promise.resolve({ wav: new Blob([new Uint8Array(64)], { type: 'audio/wav' }), seconds: 1.4, peak: 0.3, capturedSeconds: 1.4 }) }
  }
  return { ...real, WavRecorder: FakeRecorder }
})

const HEALTH = { status: 'ok', db: 'ok', products: 65, gnani_configured: true, version: '2.6.0', store_name: 'Demo' }
const AUDIO = { audio_id: 'a1', audio_url: '/api/audio/a1.wav', tts_ms: 480, cached: false, error: null }

interface Call { key: string; body: unknown }
function server(handlers: Record<string, (body: unknown, init: RequestInit) => Response | Promise<Response>>) {
  const calls: Call[] = []
  vi.stubGlobal('fetch', vi.fn().mockImplementation(async (url: string, init: RequestInit = {}) => {
    const key = `${init.method ?? 'GET'} ${url}`
    const body = typeof init.body === 'string' ? JSON.parse(init.body) : init.body ?? null
    calls.push({ key, body })
    if (key === 'GET /api/health') return json(HEALTH)
    if (key === 'GET /api/languages') return json(languages())
    const h = handlers[key]
    if (!h) throw new Error(`unmocked ${key}`)
    return h(body, init)
  }))
  return { calls, count: (k: string) => calls.filter((c) => c.key === k).length }
}
const renderIt = () => render(<MemoryRouter><TestAuth><ToastProvider><OrderDesk /></ToastProvider></TestAuth></MemoryRouter>)

const played: string[] = []
beforeEach(() => {
  played.length = 0
  vi.stubGlobal('Audio', class { onended: (() => void) | null = null; onerror: (() => void) | null = null; constructor(public src: string) { played.push(src) } play() { return Promise.resolve() } })
})
afterEach(() => { vi.unstubAllGlobals(); sessionStorage.clear(); localStorage.clear() })

async function speakOnce() {
  await userEvent.click(await screen.findByRole('button', { name: 'Tap and speak' }))
  await userEvent.click(await screen.findByRole('button', { name: 'Stop and send' }))
}

describe('OrderDesk: spoken order, reply first and voice after', () => {
  it('asks the server not to speak in the same request, shows the bill, then fetches the voice separately and plays it', async () => {
    let release: (r: Response) => void = () => undefined
    const s = server({
      'POST /api/voice/turn': () => json(turn({ transcript: 'mane 2 kilo chawal joie', language: 'gu', timings: { stt_ms: 800, nlu_ms: 0.6, tts_ms: null } })),
      'POST /api/turns/11/speak': () => new Promise<Response>((res) => { release = res }),
      'POST /api/turns/11/client-timing': () => json({ ok: true }),
    })
    renderIt()
    await speakOnce()

    // The reply and the bill are on screen while the voice has not come back yet.
    expect(await screen.findByText('2 kilo Rice add kar diya.')).toBeInTheDocument()
    expect(await screen.findByText('Preparing the voice')).toBeInTheDocument()
    expect(played).toEqual([])
    const sent = s.calls.find((c) => c.key === 'POST /api/voice/turn')!.body as FormData
    expect(sent.get('speak_reply')).toBe('false')

    release(json({ turn_id: 11, audio: AUDIO, timings: { tts_ms: 480 } }))
    await waitFor(() => expect(played).toEqual(['/api/audio/a1.wav']))
    expect(await screen.findByText('voice 480 ms')).toBeInTheDocument()
    await waitFor(() => expect(s.count('POST /api/turns/11/client-timing')).toBe(1))
    const t = s.calls.find((c) => c.key === 'POST /api/turns/11/client-timing')!.body as Record<string, unknown>
    expect(t.endpoint).toBe('manual')
    expect(typeof t.end_to_reply_ms).toBe('number')
  })

  it('keeps the written reply and says so when the voice cannot be made', async () => {
    server({
      'POST /api/voice/turn': () => json(turn({ transcript: 'x' })),
      'POST /api/turns/11/speak': () => json({ detail: 'busy' }, 503),
      'POST /api/turns/11/client-timing': () => json({ ok: true }),
    })
    renderIt()
    await speakOnce()
    expect(await screen.findByText('2 kilo Rice add kar diya.')).toBeInTheDocument()
    expect(await screen.findByText(/The reply is on screen, but its voice could not be made/)).toBeInTheDocument()
    expect(played).toEqual([])
    expect(screen.queryByText('Preparing the voice')).not.toBeInTheDocument()
  })

  it('does not ask for a voice when "Speak replies" is off', async () => {
    const s = server({
      'POST /api/voice/turn': () => json(turn({ transcript: 'x' })),
      'POST /api/turns/11/client-timing': () => json({ ok: true }),
    })
    renderIt()
    await userEvent.click(await screen.findByRole('checkbox', { name: 'Speak replies' }))
    await speakOnce()
    expect(await screen.findByText('2 kilo Rice add kar diya.')).toBeInTheDocument()
    await waitFor(() => expect(s.count('POST /api/turns/11/client-timing')).toBe(1))
    expect(s.count('POST /api/turns/11/speak')).toBe(0)
  })

  it('says nothing was heard and leaves the bill as it was when the recording had no speech', async () => {
    server({
      'POST /api/text/turn': () => json(turn()),
      'POST /api/voice/turn': () => json(turn({ no_speech: true, transcript: '', reply_text: 'I did not hear anything. Please say it again.', cart: undefined as never })),
    })
    renderIt()
    await userEvent.type(await screen.findByLabelText('Or type the order'), 'chawal')
    await userEvent.click(screen.getByRole('button', { name: 'Send' }))
    expect(await screen.findByTitle('Rice')).toBeInTheDocument()     // the bill line (shown in the customer's language, English in its tooltip)

    await speakOnce()
    expect(await screen.findByText('I did not hear anything. Please say it again.')).toBeInTheDocument()
    expect(screen.getByText('no speech heard')).toBeInTheDocument()
    expect(screen.getByTitle('Rice')).toBeInTheDocument()          // the bill from before is untouched
  })
})

describe('OrderDesk: a recording that did not get through', () => {
  it('keeps the recording after a timeout and sends the same one again on "Try again"', async () => {
    let n = 0
    const s = server({
      'POST /api/voice/turn': () => (++n === 1 ? json({ detail: 'The speech service took too long to answer. Your bill has not changed. Try again.', code: 'TIMEOUT' }, 504) : json(turn({ transcript: 'chawal' }))),
      'POST /api/turns/11/speak': () => json({ turn_id: 11, audio: AUDIO, timings: { tts_ms: 480 } }),
      'POST /api/turns/11/client-timing': () => json({ ok: true }),
    })
    renderIt()
    await speakOnce()
    expect(await screen.findByText('Your recording is kept.')).toBeInTheDocument()
    expect(screen.queryByText('2 kilo Rice add kar diya.')).not.toBeInTheDocument()

    await userEvent.click(screen.getByRole('button', { name: 'Try again' }))
    expect(await screen.findByText('2 kilo Rice add kar diya.')).toBeInTheDocument()
    expect(s.count('POST /api/voice/turn')).toBe(2)
    const [a, b] = s.calls.filter((c) => c.key === 'POST /api/voice/turn').map((c) => (c.body as FormData).get('audio') as Blob)
    expect(a.size).toBe(b.size)
    expect(screen.queryByText('Your recording is kept.')).not.toBeInTheDocument()
  })

  it('does not offer "Try again" for a refusal that will not pass (a bad request)', async () => {
    server({ 'POST /api/voice/turn': () => json({ detail: 'That audio is not a valid recording.', code: 'BAD_AUDIO' }, 400) })
    renderIt()
    await speakOnce()
    expect((await screen.findAllByText(/not a valid recording/)).length).toBeGreaterThan(0)
    expect(screen.queryByText('Your recording is kept.')).not.toBeInTheDocument()
  })

  it('offers "Try again" without calling the server while the device is offline', async () => {
    const s = server({ 'POST /api/voice/turn': () => json(turn()) })
    const online = vi.spyOn(window.navigator, 'onLine', 'get').mockReturnValue(false)
    renderIt()
    await speakOnce()
    expect(await screen.findByText('Your recording is kept.')).toBeInTheDocument()
    expect(s.count('POST /api/voice/turn')).toBe(0)
    online.mockRestore()
  })
})

describe('OrderDesk: an open bill survives leaving the page', () => {
  const snapshot = (over: Record<string, unknown> = {}) => ({
    session_id: 'sess-1', phase: 'collecting', awaiting: 'more_items', pending: null, language: 'hinglish', customer_id: null,
    cart: turn().cart, turns: [{ role: 'customer', text: 'chawal', language: 'hinglish' }, { role: 'assistant', text: '2 kilo Rice add kar diya.', language: 'hinglish' }], ...over,
  })

  it('puts the saved bill and the conversation back and says it was restored', async () => {
    saveOpenSession('sess-1')
    server({ 'GET /api/sessions/sess-1': () => json(snapshot()) })
    renderIt()
    expect(await screen.findByText('Your open bill was restored.')).toBeInTheDocument()
    expect(screen.getByText('chawal')).toBeInTheDocument()
    expect(screen.getByTitle('Rice')).toBeInTheDocument()
  })

  it('forgets a bill that was already confirmed instead of reopening it', async () => {
    saveOpenSession('sess-1')
    server({ 'GET /api/sessions/sess-1': () => json(snapshot({ phase: 'completed' })) })
    renderIt()
    await waitFor(() => expect(sessionStorage.getItem('swara.openSession')).toBeNull())
    expect(screen.queryByText('Your open bill was restored.')).not.toBeInTheDocument()
  })

  it('forgets the saved id when the server no longer has that bill', async () => {
    saveOpenSession('gone')
    server({ 'GET /api/sessions/gone': () => json({ detail: 'not found' }, 404) })
    renderIt()
    await waitFor(() => expect(sessionStorage.getItem('swara.openSession')).toBeNull())
  })

  it('"Start a new customer instead" clears the restored bill', async () => {
    saveOpenSession('sess-1')
    server({ 'GET /api/sessions/sess-1': () => json(snapshot()) })
    renderIt()
    await userEvent.click(await screen.findByRole('button', { name: 'Start a new customer instead' }))
    await waitFor(() => expect(screen.queryByText('Your open bill was restored.')).not.toBeInTheDocument())
    expect(sessionStorage.getItem('swara.openSession')).toBeNull()
    const talk = screen.getByLabelText('Conversation')
    expect(within(talk).queryByText('chawal')).not.toBeInTheDocument()
  })
})
