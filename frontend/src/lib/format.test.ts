import { describe, expect, it } from 'vitest'
import { fmtQty, istTime, itemName, ms, rupees, unitLabel } from './format'

describe('format helpers', () => {
  it('formats paise as rupees with Indian grouping and no float drift', () => {
    expect(rupees(17200)).toBe('₹172')
    expect(rupees(0)).toBe('₹0')
    expect(rupees(1667)).toBe('₹16.67')
    expect(rupees(123456700)).toBe('₹12,34,567')
    expect(rupees(5)).toBe('₹0.05')
    expect(rupees(-250)).toBe('-₹2.50')
  })
  it('trims quantities', () => {
    expect(fmtQty('2.000')).toBe('2')
    expect(fmtQty('0.250')).toBe('0.25')
    expect(fmtQty(1.5)).toBe('1.5')
  })
  it('localises unit labels', () => {
    expect(unitLabel('kg', 'gu')).toBe('કિલો')
    expect(unitLabel('l', 'hi')).toBe('लीटर')
    expect(unitLabel('pack', 'en')).toBe('pack')
    expect(unitLabel('unknown', 'en')).toBe('unknown')
    expect(unitLabel(null)).toBe('')
  })
  it('picks item names by language with English fallback', () => {
    const p = { name_en: 'Sugar', name_gu: 'ખાંડ', name_hi: '' }
    expect(itemName(p, 'gu')).toBe('ખાંડ')
    expect(itemName(p, 'hi')).toBe('Sugar')
    expect(itemName(p, 'hinglish')).toBe('Sugar')
  })
  it('formats time in IST', () => {
    expect(istTime('2026-11-10T04:30:00Z')).toMatch(/10 Nov.*10:00/)
  })
  it('formats milliseconds', () => {
    expect(ms(null)).toBe('-')
    expect(ms(420)).toBe('420 ms')
    expect(ms(1530)).toBe('1.53 s')
  })
})
