import { describe, expect, it } from 'vitest'
import { safeCell, toCsv } from './csv'

describe('csv', () => {
  it('protects text that a spreadsheet would run as a formula, but not numbers', () => {
    expect(safeCell('=SUM(A1:A9)')).toBe("'=SUM(A1:A9)")
    expect(safeCell('+91 98')).toBe("'+91 98")
    expect(safeCell('-cmd')).toBe("'-cmd")
    expect(safeCell('@x')).toBe("'@x")
    expect(safeCell('\tx')).toBe("'\tx")
    expect(safeCell(-4)).toBe('-4')
    expect(safeCell(null)).toBe('')
    expect(safeCell(NaN)).toBe('')
  })
  it('quotes commas, quotes and line breaks, starts with a byte-order mark and ends rows with CRLF', () => {
    const out = toCsv(['Name', 'Note'], [['Amul, Butter', 'say "hi"'], ['Tata\nSalt', 3]])
    expect(out.startsWith('\uFEFF')).toBe(true)
    expect(out).toBe('\uFEFFName,Note\r\n"Amul, Butter","say ""hi"""\r\n"Tata\nSalt",3\r\n')
  })
})
