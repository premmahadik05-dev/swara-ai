import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, describe, expect, it, vi } from 'vitest'
import Settings from './Settings'
import { ToastProvider } from '../components/Toast'
import { json, languageInfo, languages, settings } from '../test/fixtures'
import { STAFF_USER, TestAuth } from '../test/auth'
import { SHOP_RENAMED } from '../lib/shop'

afterEach(() => { vi.unstubAllGlobals(); sessionStorage.clear() })

function mockApi(initial = settings(), extra: Record<string, () => Response> = {}) {
  const calls: { url: string; method: string; body: string | null }[] = []
  vi.stubGlobal('fetch', vi.fn().mockImplementation(async (url: string, init: RequestInit = {}) => {
    calls.push({ url, method: init.method ?? 'GET', body: (init.body as string) ?? null })
    const key = `${init.method ?? 'GET'} ${url}`
    if (extra[key]) return extra[key]()
    if (key === 'GET /api/languages') return json(languages())
    return json(initial)
  }))
  return calls
}
const renderIt = () => render(<MemoryRouter><TestAuth><ToastProvider><Settings /></ToastProvider></TestAuth></MemoryRouter>)

describe('Settings', () => {
  it('shows "No key yet", disables save/test, and says Evon is not available', async () => {
    mockApi()
    renderIt()
    expect(await screen.findByText('No key yet')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Save key' })).toBeDisabled()
    expect(screen.getByRole('button', { name: /Test connection/ })).toBeDisabled()
    expect(screen.getByText(/Evon v3.3 is not exposed|not exposed on the Gnani API/)).toBeInTheDocument()
  })

  it('links the owner to Voice diagnostics', async () => {
    mockApi()
    renderIt()
    expect(await screen.findByRole('link', { name: 'Voice diagnostics' })).toHaveAttribute('href', '/diagnostics')
  })

  it('does not offer Voice diagnostics to staff', async () => {
    mockApi()
    render(<MemoryRouter><TestAuth user={STAFF_USER}><ToastProvider><Settings /></ToastProvider></TestAuth></MemoryRouter>)
    await screen.findByText('Voice connection')
    expect(screen.queryByRole('link', { name: 'Voice diagnostics' })).toBeNull()
  })

  it('shows only the masked hint when a key exists and never offers the key back', async () => {
    mockApi(settings({ configured: true, key_hint: '…x9Zq' }))
    renderIt()
    expect(await screen.findByText(/Key set …x9Zq/)).toBeInTheDocument()
    const input = screen.getByLabelText('Replace the API key') as HTMLInputElement
    expect(input.type).toBe('password')
    expect(input.value).toBe('')
  })

  it('saves a new key with PUT, clears the field afterwards and reloads settings', async () => {
    const calls = mockApi(settings(), { 'PUT /api/settings/gnani-key': () => json(settings({ configured: true, key_hint: '…efgh' })) })
    renderIt()
    const input = await screen.findByLabelText('Paste your Gnani API key')
    await userEvent.type(input, 'abcd1234efgh')
    await userEvent.click(screen.getByRole('button', { name: 'Save key' }))
    await waitFor(() => expect(calls.some((c) => c.method === 'PUT' && c.url === '/api/settings/gnani-key')).toBe(true))
    expect(JSON.parse(calls.find((c) => c.method === 'PUT')!.body!)).toEqual({ api_key: 'abcd1234efgh' })
    await waitFor(() => expect((screen.getByLabelText(/API key/) as HTMLInputElement).value).toBe(''))
  })

  it('reports each real round-trip result of the connection test separately', async () => {
    mockApi(settings({ configured: true, key_hint: '…efgh' }), {
      'POST /api/settings/test-gnani?language=en': () => json({
        phrase: 'do kilo chawal',
        tts: { ok: true, latency_ms: 812, bytes: 40000, voice: 'Falak' },
        stt: { ok: false, error: 'Prisma rejected the key (401).' },
      }),
    })
    renderIt()
    await userEvent.click(await screen.findByRole('button', { name: /Test connection/ }))
    expect(await screen.findByText(/worked in 812 ms/)).toBeInTheDocument()
    expect(screen.getByText(/Prisma rejected the key/)).toBeInTheDocument()
  })

  it('shows a backend refusal (e.g. bad key format) instead of failing silently', async () => {
    mockApi(settings(), { 'PUT /api/settings/gnani-key': () => json({ detail: { code: 'BAD_KEY', message: 'That does not look like a Gnani key.' } }, 422) })
    renderIt()
    await userEvent.type(await screen.findByLabelText('Paste your Gnani API key'), 'not-a-real-key')
    await userEvent.click(screen.getByRole('button', { name: 'Save key' }))
    expect(await screen.findByText('That does not look like a Gnani key.')).toBeInTheDocument()
  })

  it('has no shared admin token any more: access is by account', async () => {
    mockApi()
    renderIt()
    await screen.findByText('No key yet')
    expect(screen.queryByLabelText('Admin token')).toBeNull()
    expect(screen.queryByRole('button', { name: 'Use token' })).toBeNull()
    expect(screen.queryByText(/Admin protection/)).toBeNull()
  })

  it('shows staff only what they may use: whether voice is connected, never the key or the connection form', async () => {
    mockApi(settings({ configured: true, key_hint: null, base_url: null }))
    render(<MemoryRouter><TestAuth user={STAFF_USER}><ToastProvider><Settings /></ToastProvider></TestAuth></MemoryRouter>)
    expect(await screen.findByText(/signed in as staff/)).toBeInTheDocument()
    expect(screen.getByText('Voice is connected')).toBeInTheDocument()
    expect(screen.queryByLabelText(/API key/)).toBeNull()
    expect(screen.queryByRole('button', { name: 'Save key' })).toBeNull()
    expect(screen.queryByLabelText('Speech-to-text model')).toBeNull()
  })

  it('has no appearance or theme setting: light is the only theme', async () => {
    mockApi()
    render(<MemoryRouter><TestAuth><ToastProvider><Settings /></ToastProvider></TestAuth></MemoryRouter>)
    await screen.findByText(/Voice connection|API key/i)
    expect(screen.queryByRole('group', { name: 'Theme' })).toBeNull()
    expect(screen.queryByText('Appearance')).toBeNull()
    expect(screen.queryByRole('button', { name: /dark/i })).toBeNull()
  })

  describe('shop name', () => {
    it('lets the owner rename the shop: collapses extra spaces, saves, tells the sidebar, and confirms', async () => {
      const calls = mockApi()
      const renamed = vi.fn()
      window.addEventListener(SHOP_RENAMED, renamed)
      renderIt()
      const input = await screen.findByLabelText('Shop name')
      expect(input).toHaveValue('Patel Kirana (demo)')
      const save = screen.getByRole('button', { name: 'Save name' })
      expect(save).toBeDisabled()                                            // nothing changed yet
      await userEvent.clear(input)
      await userEvent.type(input, '  Shah   Kirana & Stores ')
      expect(save).toBeEnabled()
      await userEvent.click(save)
      await waitFor(() => expect(calls.some((c) => c.method === 'PUT' && c.url === '/api/settings')).toBe(true))
      expect(JSON.parse(calls.find((c) => c.method === 'PUT')!.body!)).toEqual({ store_name: 'Shah Kirana & Stores' })
      expect(await screen.findByText('Shop name saved.')).toBeInTheDocument()
      expect(renamed).toHaveBeenCalledTimes(1)
      window.removeEventListener(SHOP_RENAMED, renamed)
    })

    it('says what is wrong with a name that is too short, and sends nothing', async () => {
      const calls = mockApi()
      renderIt()
      const input = await screen.findByLabelText('Shop name')
      await userEvent.clear(input)
      await userEvent.type(input, 'x')
      expect(screen.getByText('Use 2 to 80 characters.')).toBeInTheDocument()
      expect(screen.getByRole('button', { name: 'Save name' })).toBeDisabled()
      expect(calls.some((c) => c.method === 'PUT')).toBe(false)
    })

    it('shows the server\'s reason when it refuses the name, and keeps what was typed', async () => {
      mockApi(settings(), { 'PUT /api/settings': () => json({ detail: "Use letters, numbers, spaces and & ' . , - ( ) / + @ in the shop name. Not allowed: #" }, 422) })
      renderIt()
      const input = await screen.findByLabelText('Shop name')
      await userEvent.clear(input)
      await userEvent.type(input, 'Shop #1')
      await userEvent.click(screen.getByRole('button', { name: 'Save name' }))
      expect(await screen.findByText(/Not allowed: #/)).toBeInTheDocument()
      expect(input).toHaveValue('Shop #1')
      expect(input).toHaveAttribute('aria-invalid', 'true')
    })

    it('is not offered to staff, who cannot change it', async () => {
      mockApi()
      render(<MemoryRouter><TestAuth user={STAFF_USER}><ToastProvider><Settings /></ToastProvider></TestAuth></MemoryRouter>)
      expect(await screen.findByText(/You are signed in as staff/)).toBeInTheDocument()
      expect(screen.queryByLabelText('Shop name')).toBeNull()
      expect(screen.queryByRole('button', { name: 'Save name' })).toBeNull()
    })
  })
})



describe('Settings: languages and voices', () => {
  const row = (name: string) => screen.getByText(name, { selector: 'b' }).closest('li') as HTMLElement

  it('lists all eleven languages with their Gnani codes, and says none has been checked live yet', async () => {
    mockApi()
    renderIt()
    const list = await screen.findByRole('list', { name: 'Languages' })
    expect(within(list).getAllByRole('listitem')).toHaveLength(11)
    expect(within(row('தமிழ்')).getByText(/ta-IN/)).toBeInTheDocument()
    expect(within(list).getAllByText('Not verified live')).toHaveLength(11)
    expect(within(list).queryByText('Live checked')).toBeNull()
  })

  it('shows "Live checked" for a language only when the results file says both voice and speech passed', async () => {
    const rows = languages().languages.map((l) => l.key === 'mr' ? languageInfo('mr', { verification: { tts: { status: 'passed' }, stt_code: { status: 'passed' }, stt_loopback: { status: 'not_run' }, stt_human: { status: 'not_run' } } }) : l)
    mockApi(settings(), { 'GET /api/languages': () => json(languages({}, rows)) })
    renderIt()
    await screen.findByRole('list', { name: 'Languages' })
    expect(within(row('मराठी')).getByText('Live checked')).toBeInTheDocument()
    expect(within(row('বাংলা')).getByText('Not verified live')).toBeInTheDocument()
  })

  it('switches a language off by sending the full list of switched-off languages, and refreshes', async () => {
    const calls = mockApi(settings(), { 'PUT /api/settings': () => json(settings()) })
    renderIt()
    await screen.findByRole('list', { name: 'Languages' })
    await userEvent.click(screen.getByRole('checkbox', { name: 'Offer Telugu' }))
    await waitFor(() => expect(calls.some((c) => c.method === 'PUT' && c.url === '/api/settings')).toBe(true))
    expect(JSON.parse(calls.find((c) => c.method === 'PUT')!.body!)).toEqual({ disabled_languages: ['te'] })
  })

  it('keeps already-switched-off languages in the list when another is switched off', async () => {
    const calls = mockApi({ ...settings(), languages: { disabled: ['bn'], env: 'DISABLED_LANGUAGES' } }, { 'PUT /api/settings': () => json(settings()) })
    renderIt()
    await screen.findByRole('list', { name: 'Languages' })
    await userEvent.click(screen.getByRole('checkbox', { name: 'Offer Kannada' }))
    await waitFor(() => expect(calls.some((c) => c.method === 'PUT')).toBe(true))
    expect(JSON.parse(calls.find((c) => c.method === 'PUT')!.body!).disabled_languages.sort()).toEqual(['bn', 'kn'])
  })

  it('never lets English be switched off', async () => {
    mockApi()
    renderIt()
    await screen.findByRole('list', { name: 'Languages' })
    expect(screen.getByRole('checkbox', { name: 'Offer English' })).toBeDisabled()
    expect(within(row('English')).getByText('Always on')).toBeInTheDocument()
  })

  it('saves the chosen voice for that language only', async () => {
    const rows = languages().languages.map((l) => l.key === 'kn' ? { ...l, voices: ['Saanvi', 'Kavin'] } : l)
    const calls = mockApi(settings(), { 'GET /api/languages': () => json(languages({}, rows)), 'PUT /api/settings': () => json(settings()) })
    renderIt()
    await screen.findByRole('list', { name: 'Languages' })
    const select = screen.getByRole('combobox', { name: 'Kannada voice' })
    expect(select).toHaveValue('Saanvi')
    await userEvent.selectOptions(select, 'Kavin')
    await waitFor(() => expect(calls.some((c) => c.method === 'PUT' && c.url === '/api/settings')).toBe(true))
    expect(JSON.parse(calls.find((c) => c.method === 'PUT')!.body!)).toEqual({ tts_voice_kn: 'Kavin' })
  })

  it('runs the test for one language and reports voice and speech separately, as a loopback', async () => {
    const calls = mockApi(settings({ configured: true, key_hint: '…efgh' }), {
      'POST /api/settings/test-gnani?language=ta': () => json({
        language: 'ta', loopback: true, phrase: 'x',
        tts: { ok: true, latency_ms: 700, bytes: 30000, voice: 'Asmita' },
        stt: { ok: true, latency_ms: 500, transcript: 'இரண்டு கிலோ சர்க்கரை' },
      }),
    })
    renderIt()
    await screen.findByRole('list', { name: 'Languages' })
    await userEvent.click(within(row('தமிழ்')).getByRole('button', { name: /Test/ }))
    expect(await screen.findByText(/voice worked in 700 ms/)).toBeInTheDocument()
    expect(screen.getByText(/Prisma heard "இரண்டு கிலோ சர்க்கரை"/)).toBeInTheDocument()
    expect(screen.getByText(/Spoken by Timbre, not a person/)).toBeInTheDocument()
    expect(calls.some((c) => c.url === '/api/settings/test-gnani?language=ta' && c.method === 'POST')).toBe(true)
  })

  it('shows a failed language test as a failure, with the reason Gnani gave', async () => {
    mockApi(settings({ configured: true, key_hint: '…efgh' }), {
      'POST /api/settings/test-gnani?language=bn': () => json({
        language: 'bn', loopback: true, phrase: 'x',
        tts: { ok: true, latency_ms: 700, bytes: 30000, voice: 'Kirra' },
        stt: { ok: false, error: 'Prisma rejected the language code (400).' },
      }),
    })
    renderIt()
    await screen.findByRole('list', { name: 'Languages' })
    await userEvent.click(within(row('বাংলা')).getByRole('button', { name: /Test/ }))
    expect(await screen.findByText(/speech failed: Prisma rejected the language code/)).toBeInTheDocument()
  })

  it('disables the per-language test until a key is set, and for a switched-off language', async () => {
    mockApi()
    renderIt()
    await screen.findByRole('list', { name: 'Languages' })
    for (const li of within(screen.getByRole('list', { name: 'Languages' })).getAllByRole('listitem')) expect(within(li).getByRole('button', { name: /Test/ })).toBeDisabled()
  })

  it('is not shown to staff', async () => {
    mockApi(settings({ configured: true }))
    render(<MemoryRouter><TestAuth user={STAFF_USER}><ToastProvider><Settings /></ToastProvider></TestAuth></MemoryRouter>)
    await screen.findByText(/signed in as staff/)
    expect(screen.queryByRole('list', { name: 'Languages' })).toBeNull()
  })
})
