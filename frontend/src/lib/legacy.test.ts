import { beforeEach, describe, expect, it } from 'vitest'
import { migrateLegacyStorage } from './legacy'

describe('migrateLegacyStorage', () => {
  beforeEach(() => { localStorage.clear(); sessionStorage.clear() })

  it('moves settings saved under the old product name to the new keys and removes the old ones', () => {
    localStorage.setItem('dukaanmitra.includeDemo', '0')
    localStorage.setItem('dukaanmitra.sidebar', '1')
    migrateLegacyStorage()
    expect(localStorage.getItem('swara.includeDemo')).toBe('0')
    expect(localStorage.getItem('swara.sidebar')).toBe('1')
    expect(localStorage.getItem('dukaanmitra.includeDemo')).toBeNull()
  })

  it('deletes a saved theme choice instead of moving it: there is no dark theme any more', () => {
    localStorage.setItem('dukaanmitra.theme', 'dark')
    localStorage.setItem('swara.theme', 'dark')
    migrateLegacyStorage()
    expect(localStorage.getItem('swara.theme')).toBeNull()
    expect(localStorage.getItem('dukaanmitra.theme')).toBeNull()
  })

  it('removes a leftover shared admin token: accounts replaced it and nothing reads it any more', () => {
    sessionStorage.setItem('swara.adminToken', 'tok')
    sessionStorage.setItem('dukaanmitra.adminToken', 'tok2')
    migrateLegacyStorage()
    expect(sessionStorage.length).toBe(0)
  })

  it('never overwrites a value the person has already set under the new name', () => {
    localStorage.setItem('swara.sidebar', '0')
    localStorage.setItem('dukaanmitra.sidebar', '1')
    migrateLegacyStorage()
    expect(localStorage.getItem('swara.sidebar')).toBe('0')
    expect(localStorage.getItem('dukaanmitra.sidebar')).toBeNull()
  })

  it('does nothing when there is nothing to move', () => {
    migrateLegacyStorage()
    expect(localStorage.length).toBe(0)
    expect(sessionStorage.length).toBe(0)
  })
})
