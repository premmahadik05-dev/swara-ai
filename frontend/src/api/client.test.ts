import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { ApiError, api, clearApiCache, csrfToken, setUnauthorizedHandler, toApiError } from './client'
import { json } from '../test/fixtures'

afterEach(() => { vi.restoreAllMocks(); vi.unstubAllGlobals(); sessionStorage.clear(); csrfToken.set(null); setUnauthorizedHandler(null) })

describe('toApiError', () => {
  it('reads the {detail:{code,message}} envelope the backend uses', async () => {
    const e = await toApiError(json({ detail: { code: 'NOT_CONFIGURED', message: 'Add your Gnani key.' } }, 503))
    expect(e).toBeInstanceOf(ApiError)
    expect([e.status, e.code, e.message]).toEqual([503, 'NOT_CONFIGURED', 'Add your Gnani key.'])
  })
  it('reads plain string and validation-array details', async () => {
    expect((await toApiError(json({ detail: 'Nope' }, 400))).message).toBe('Nope')
    const v = await toApiError(json({ detail: [{ msg: 'field required' }, { msg: 'bad qty' }, { msg: 'third' }] }, 422))
    expect(v.message).toBe('field required; bad qty')
  })
  it('gives actionable text for 401, 403 and 429 without a body message', async () => {
    expect((await toApiError(json({}, 401))).message).toMatch(/Sign in/)
    expect((await toApiError(json({}, 403))).message).toMatch(/permission/)
    expect((await toApiError(json({}, 429))).message).toMatch(/Too many requests/)
  })
  it('survives a non-JSON body', async () => {
    const e = await toApiError(new Response('<html>boom</html>', { status: 502, statusText: 'Bad Gateway' }))
    expect(e.status).toBe(502)
    expect(e.message).toBe('Bad Gateway')
  })
})

describe('request layer', () => {
  beforeEach(() => { sessionStorage.clear() })

  it('turns a dead server into a clear NETWORK error', async () => {
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new TypeError('Failed to fetch')))
    await expect(api.health()).rejects.toMatchObject({ code: 'NETWORK', status: 0 })
  })

  it('sends the CSRF token on writes only, and never reads or writes any stored credential', async () => {
    const f = vi.fn().mockImplementation(async () => json({ status: 'ok' }))
    vi.stubGlobal('fetch', f)
    await api.health()
    expect(new Headers(f.mock.calls[0][1].headers).has('X-CSRF-Token')).toBe(false)
    await api.newSession()
    expect(new Headers(f.mock.calls[1][1].headers).has('X-CSRF-Token')).toBe(false)     // not signed in yet: nothing to send
    csrfToken.set('csrf-123')
    clearApiCache()
    await api.health()
    expect(new Headers(f.mock.calls[2][1].headers).has('X-CSRF-Token')).toBe(false)     // reads do not need it
    await api.newSession()
    expect(new Headers(f.mock.calls[3][1].headers).get('X-CSRF-Token')).toBe('csrf-123')
    expect(sessionStorage.length + localStorage.length).toBe(0)                          // the token lives in memory only
  })

  it('tells the app when a protected call finds the session gone, but not for the sign-in form itself', async () => {
    const gone = vi.fn()
    setUnauthorizedHandler(gone)
    vi.stubGlobal('fetch', vi.fn().mockImplementation(async () => json({ detail: { code: 'SESSION_EXPIRED', message: 'Your session has ended.' } }, 401)))
    await expect(api.orders({})).rejects.toMatchObject({ status: 401, code: 'SESSION_EXPIRED' })
    expect(gone).toHaveBeenCalledWith('SESSION_EXPIRED')
    gone.mockClear()
    vi.stubGlobal('fetch', vi.fn().mockImplementation(async () => json({ detail: { code: 'INVALID_CREDENTIALS', message: 'Incorrect e-mail or password.' } }, 401)))
    await expect(api.signIn({ email: 'a@b.co', password: 'x', remember: false })).rejects.toMatchObject({ code: 'INVALID_CREDENTIALS' })
    expect(gone).not.toHaveBeenCalled()
  })

  it('posts JSON for text turns and never sends an empty session id', async () => {
    const f = vi.fn().mockImplementation(async () => json({ ok: true }))
    vi.stubGlobal('fetch', f)
    await api.textTurn('do kilo chawal', null)
    const [url, init] = f.mock.calls[0]
    expect(url).toBe('/api/text/turn')
    expect(JSON.parse(init.body)).toEqual({ text: 'do kilo chawal', speak: false })
    expect(new Headers(init.headers).get('Content-Type')).toBe('application/json')
  })

  it('builds query strings that skip empty values', async () => {
    const f = vi.fn().mockImplementation(async () => json([]))
    vi.stubGlobal('fetch', f)
    await api.products({ q: 'dal', category: '', status: undefined })
    expect(f.mock.calls[0][0]).toBe('/api/products?q=dal')
    await api.overview(7, false)
    expect(f.mock.calls[1][0]).toBe('/api/analytics/overview?days=7&include_synthetic=false')
  })

  it('sends the API key in the JSON body of PUT, never in the URL', async () => {
    const f = vi.fn().mockImplementation(async () => json({}))
    vi.stubGlobal('fetch', f)
    await api.putKey('abcd1234efgh')
    const [url, init] = f.mock.calls[0]
    expect(url).toBe('/api/settings/gnani-key')
    expect(String(url)).not.toContain('abcd1234')
    expect(init.method).toBe('PUT')
    expect(JSON.parse(init.body)).toEqual({ api_key: 'abcd1234efgh' })
  })
})

describe('GET de-duplication and cache', () => {
  it('shares one network call between identical GETs that are in flight', async () => {
    let release!: () => void
    const gate = new Promise<void>((r) => { release = r })
    const f = vi.fn().mockImplementation(async () => { await gate; return json([]) })
    vi.stubGlobal('fetch', f)
    const a = api.sessions(5), b = api.sessions(5), c = api.sessions(6)
    release()
    await Promise.all([a, b, c])
    expect(f).toHaveBeenCalledTimes(2)   // limit=5 once, limit=6 once
  })

  it('keeps slow-changing lookups briefly, and a write clears them so nothing stale is shown', async () => {
    const f = vi.fn().mockImplementation(async () => json({ ok: true }))
    vi.stubGlobal('fetch', f)
    await api.categories(); await api.categories()
    expect(f).toHaveBeenCalledTimes(1)
    await api.newSession()                 // a POST
    await api.categories()
    expect(f).toHaveBeenCalledTimes(3)     // categories, POST, categories again
  })

  it('does not cache data that changes with every order', async () => {
    const f = vi.fn().mockImplementation(async () => json([]))
    vi.stubGlobal('fetch', f)
    await api.alerts(); await api.alerts()
    expect(f).toHaveBeenCalledTimes(2)
  })

  it('does not keep a failed request around', async () => {
    const f = vi.fn().mockRejectedValueOnce(new TypeError('down')).mockImplementation(async () => json({ status: 'ok' }))
    vi.stubGlobal('fetch', f)
    await expect(api.health()).rejects.toMatchObject({ code: 'NETWORK' })
    await expect(api.health()).resolves.toMatchObject({ status: 'ok' })
  })
})


describe('language-aware calls', () => {
  it('sends the language hint with a typed turn and with the live parser, and omits it when there is none', async () => {
    const f = vi.fn().mockImplementation(async () => json({ ok: true }))
    vi.stubGlobal('fetch', f)
    await api.textTurn('मला दोन किलो साखर पाहिजे', null, false, null, 'mr')
    expect(JSON.parse(f.mock.calls[0][1].body)).toEqual({ text: 'मला दोन किलो साखर पाहिजे', speak: false, language: 'mr' })
    await api.textTurn('do kilo chawal', null)
    expect(JSON.parse(f.mock.calls[1][1].body)).not.toHaveProperty('language')
    await api.parse('இரண்டு கிலோ', 'ta')
    expect(f.mock.calls[2][0]).toBe('/api/text/parse')
    expect(JSON.parse(f.mock.calls[2][1].body)).toEqual({ text: 'இரண்டு கிலோ', language: 'ta' })
    await api.parse('two kilo rice')
    expect(JSON.parse(f.mock.calls[3][1].body)).not.toHaveProperty('language')
  })

  it('asks the server for the language list (cached briefly) and names the language in the connection test', async () => {
    const f = vi.fn().mockImplementation(async () => json({ languages: [] }))
    vi.stubGlobal('fetch', f)
    await api.languages()
    expect(f.mock.calls[0][0]).toBe('/api/languages')
    await api.testGnani()
    expect([f.mock.calls[1][0], f.mock.calls[1][1].method]).toEqual(['/api/settings/test-gnani?language=en', 'POST'])
    await api.testGnani('pa')
    expect(f.mock.calls[2][0]).toBe('/api/settings/test-gnani?language=pa')
  })

  it('carries the server\'s language error codes through unchanged so the screen can react to them', async () => {
    for (const code of ['LANGUAGE_DISABLED', 'AUTO_DETECT_NEEDS_V3', 'BAD_LANGUAGE']) {
      vi.stubGlobal('fetch', vi.fn().mockImplementation(async () => json({ detail: { code, message: 'x' } }, 422)))
      await expect(api.textTurn('x', null, false, null, 'bn')).rejects.toMatchObject({ code, status: 422 })
    }
  })
})
