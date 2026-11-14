/* CSV for tables that exist only in the browser (the evaluation and stock-movement tables). Mirrors backend/app/services/export.py:
   a text cell that starts with = + - @ (or tab / carriage return) gets a leading apostrophe so a spreadsheet shows it as written,
   numbers are written as numbers, and the file starts with a byte-order mark so Excel on Windows reads Gujarati and Hindi as UTF-8. */
const FORMULA_START = /^[=+\-@\t\r]/

export const safeCell = (v: string | number | null | undefined): string => {
  if (v === null || v === undefined) return ''
  if (typeof v === 'number') return Number.isFinite(v) ? String(v) : ''
  return FORMULA_START.test(v) ? `'${v}` : v
}

const quote = (s: string) => (/[",\r\n]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s)

export function toCsv(head: string[], rows: (string | number | null | undefined)[][]): string {
  const lines = [head.map((h) => quote(safeCell(h))).join(','), ...rows.map((r) => r.map((c) => quote(safeCell(c))).join(','))]
  return '\uFEFF' + lines.join('\r\n') + '\r\n'
}
