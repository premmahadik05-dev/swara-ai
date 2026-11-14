import { renderHook, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { clearApiCache } from '../api/client'
import { firstEnabled, useLanguages } from './useLanguages'
import { LANG_KEYS } from './languages'
import { json, languageInfo, languages } from '../test/fixtures'

beforeEach(() => clearApiCache())
afterEach(() => { vi.unstubAllGlobals(); clearApiCache() })

describe('useLanguages', () => {
  it('joins the server list to the names the screens know', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(json(languages())))
    const { result } = renderHook(() => useLanguages())
    await waitFor(() => expect(result.current.data).not.toBeNull())
    expect(result.current.options.map((o) => o.key)).toEqual([...LANG_KEYS])
    expect(result.current.options.find((o) => o.key === 'ta')?.info?.stt_code).toBe('ta-IN')
    expect(result.current.enabledKeys).toHaveLength(11)
  })
  it('leaves a switched-off language out of the enabled list but still shows it', async () => {
    const rows = languages().languages.map((l) => (l.key === 'bn' ? { ...l, enabled: false } : l))
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(json(languages({ disabled: ['bn'] }, rows))))
    const { result } = renderHook(() => useLanguages())
    await waitFor(() => expect(result.current.data).not.toBeNull())
    expect(result.current.enabledKeys).not.toContain('bn')
    expect(result.current.options.find((o) => o.key === 'bn')?.enabled).toBe(false)
  })
  it('still lists every language, without claims about them, when the server cannot be reached', async () => {
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new TypeError('Failed to fetch')))
    const { result } = renderHook(() => useLanguages())
    await waitFor(() => expect(result.current.error).not.toBeNull())
    expect(result.current.options).toHaveLength(11)
    expect(result.current.options.every((o) => o.info === undefined)).toBe(true)
    expect(result.current.modes[0].available).toBe(false)
  })
  it('survives a reply with the wrong shape', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(json({ languages: { nope: true }, modes: 'x' })))
    const { result } = renderHook(() => useLanguages())
    await waitFor(() => expect(result.current.loading).toBe(false))
    expect(result.current.options).toHaveLength(11)
  })
})

describe('firstEnabled', () => {
  it('falls back to the first language that is on, and to English if nothing is', () => {
    const opts = (off: string[]) => LANG_KEYS.map((k) => ({ ...languageInfo(k), enabled: !off.includes(k), info: undefined, html: k, name: k, native: k, script: '', origin: 'original' as const }))
    expect(firstEnabled(opts(['gu']) as never)).toBe('hi')
    expect(firstEnabled(opts([...LANG_KEYS]) as never)).toBe('en')
  })
})
