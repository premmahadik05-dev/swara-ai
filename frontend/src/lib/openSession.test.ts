import { afterEach, describe, expect, it, vi } from 'vitest'
import { clearOpenSession, loadOpenSession, saveOpenSession } from './openSession'

afterEach(() => { vi.useRealTimers(); vi.restoreAllMocks(); sessionStorage.clear() })

describe('openSession', () => {
  it('remembers the id of the open bill and gives it back', () => {
    saveOpenSession('abc123')
    expect(loadOpenSession()).toBe('abc123')
  })

  it('returns nothing when no bill is open, and after it is cleared', () => {
    expect(loadOpenSession()).toBeNull()
    saveOpenSession('abc123'); clearOpenSession()
    expect(loadOpenSession()).toBeNull()
  })

  it('lets a bill go after six hours', () => {
    vi.useFakeTimers(); vi.setSystemTime(new Date('2026-11-11T05:00:00Z'))
    saveOpenSession('abc123')
    vi.setSystemTime(new Date('2026-11-11T10:59:00Z'))
    expect(loadOpenSession()).toBe('abc123')
    vi.setSystemTime(new Date('2026-11-11T11:01:00Z'))
    expect(loadOpenSession()).toBeNull()
    expect(sessionStorage.getItem('swara.openSession')).toBeNull()
  })

  it.each([
    ['not json', '{oops'], ['an id with path characters', JSON.stringify({ id: '../x', at: Date.now() })],
    ['a number id', JSON.stringify({ id: 5, at: Date.now() })], ['no time', JSON.stringify({ id: 'abc' })], ['too long', JSON.stringify({ id: 'a'.repeat(41), at: Date.now() })],
  ])('rejects stored data that is %s rather than sending it to the server', (_n, raw) => {
    sessionStorage.setItem('swara.openSession', raw)
    expect(loadOpenSession()).toBeNull()
  })

  it('does not throw when storage is unavailable', () => {
    vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => { throw new Error('denied') })
    vi.spyOn(Storage.prototype, 'getItem').mockImplementation(() => { throw new Error('denied') })
    expect(() => saveOpenSession('abc')).not.toThrow()
    expect(loadOpenSession()).toBeNull()
  })
})
