import type { Lang } from '../types'
import { LANG_META } from './languages'

/** Integer paise -> "₹1,720" or "₹1,720.50". Never uses floating point for money. */
export function rupees(paise: number): string {
  const neg = paise < 0
  const abs = Math.abs(Math.round(paise))
  const whole = Math.floor(abs / 100)
  const frac = abs % 100
  const w = whole.toLocaleString('en-IN')
  return `${neg ? '-' : ''}₹${w}${frac ? '.' + String(frac).padStart(2, '0') : ''}`
}

export function fmtQty(q: number | string): string {
  const n = typeof q === 'string' ? Number(q) : q
  if (!Number.isFinite(n)) return String(q)
  return String(Math.round(n * 1000) / 1000)
}

const UNIT: Record<string, Partial<Record<Lang, string>>> = {
  kg: { gu: 'કિલો', hi: 'किलो', hinglish: 'kg', en: 'kg', mr: 'किलो', bn: 'কেজি', ta: 'கிலோ', te: 'కిలో', kn: 'ಕಿಲೋ', ml: 'കിലോ', pa: 'ਕਿਲੋ' },
  l: { gu: 'લિટર', hi: 'लीटर', hinglish: 'litre', en: 'L', mr: 'लिटर', bn: 'লিটার', ta: 'லிட்டர்', te: 'లీటర్', kn: 'ಲೀಟರ್', ml: 'ലിറ്റർ', pa: 'ਲੀਟਰ' },
  pack: { gu: 'પેકેટ', hi: 'पैकेट', hinglish: 'packet', en: 'pack', mr: 'पॅकेट', bn: 'প্যাকেট', ta: 'பாக்கெட்', te: 'ప్యాకెట్', kn: 'ಪ್ಯಾಕೆಟ್', ml: 'പാക്കറ്റ്', pa: 'ਪੈਕੇਟ' },
  pc: { gu: 'નંગ', hi: 'नग', hinglish: 'pc', en: 'pc', mr: 'नग', bn: 'পিস', ta: 'பீஸ்', te: 'పీస్', kn: 'ಪೀಸ್', ml: 'എണ്ണം', pa: 'ਪੀਸ' },
  g: { gu: 'ગ્રામ', hi: 'ग्राम', hinglish: 'gram', en: 'g', mr: 'ग्रॅम', bn: 'গ্রাম', ta: 'கிராம்', te: 'గ్రాము', kn: 'ಗ್ರಾಂ', ml: 'ഗ്രാം', pa: 'ਗ੍ਰਾਮ' },
  dozen: { gu: 'ડઝન', hi: 'दर्जन', hinglish: 'dozen', en: 'dozen', mr: 'डझन', bn: 'ডজন', ta: 'டஜன்', te: 'డజను', kn: 'ಡಜನ್', ml: 'ഡസൻ', pa: 'ਦਰਜਨ' },
}
export function unitLabel(unit: string | null | undefined, lang: Lang = 'en'): string {
  if (!unit) return ''
  return UNIT[unit]?.[lang] ?? UNIT[unit]?.en ?? unit
}

/** Language names for badges and filters. Built from the same table the language selector uses (lib/languages.ts). */
export const LANG_NAME: Record<string, string> = { ...Object.fromEntries(LANG_META.map((l) => [l.key, l.native])), auto: 'Auto', mixed: 'Gujarati + English' }
export const LANG_LATIN: Record<string, string> = Object.fromEntries(LANG_META.map((l) => [l.key, l.name]))

/** A product's name for the language being used on the bill: its own script where the product has a name in it, English otherwise. */
export function itemName(l: { name_en: string; name_gu: string; name_hi: string; names?: Partial<Record<Lang, string>> }, lang: Lang): string {
  if (lang === 'gu' && l.name_gu) return l.name_gu
  if (lang === 'hi' && l.name_hi) return l.name_hi
  return l.names?.[lang] || l.name_en
}

/** "2026-11-10T04:30:00Z" -> "10 Nov, 10:00 am" in the shop's time zone (IST). */
export function istTime(iso: string): string {
  const d = new Date(iso)
  return d.toLocaleString('en-IN', { timeZone: 'Asia/Kolkata', day: 'numeric', month: 'short', hour: 'numeric', minute: '2-digit', hour12: true })
}

export function ms(v: number | null | undefined): string {
  if (v === null || v === undefined) return '-'
  if (v >= 1000) return `${(v / 1000).toFixed(2)} s`
  return v < 1 ? '<1 ms' : `${Math.round(v)} ms`
}

/** "₹1.2L" / "₹4.5K" for chart axes and tight spaces. Whole rupees below ₹1,000. */
export function compactRupees(paise: number): string {
  const r = paise / 100
  if (r >= 10_000_000) return `₹${(r / 10_000_000).toFixed(1)}Cr`
  if (r >= 100_000) return `₹${(r / 100_000).toFixed(1)}L`
  if (r >= 1000) return `₹${(r / 1000).toFixed(r >= 10_000 ? 0 : 1)}K`
  return `₹${Math.round(r)}`
}
/** Whole-rupee display for KPIs (no paise noise on big numbers). */
export const wholeRupees = (paise: number) => `₹${Math.round(paise / 100).toLocaleString('en-IN')}`

export function istDate(iso: string): string {
  return new Date(iso).toLocaleDateString('en-IN', { timeZone: 'Asia/Kolkata', day: 'numeric', month: 'short', year: 'numeric' })
}
/** "5 min ago", "2 h ago", "3 d ago", else the date. */
export function ago(iso: string | null | undefined, now = Date.now()): string {
  if (!iso) return 'never'
  const s = Math.max(0, (now - new Date(iso).getTime()) / 1000)
  if (s < 60) return 'just now'
  if (s < 3600) return `${Math.floor(s / 60)} min ago`
  if (s < 86400) return `${Math.floor(s / 3600)} h ago`
  if (s < 86400 * 14) return `${Math.floor(s / 86400)} d ago`
  return istDate(iso)
}
export function initials(name: string): string {
  const parts = name.trim().split(/\s+/).filter(Boolean)
  return ((parts[0]?.[0] ?? '?') + (parts.length > 1 ? parts[parts.length - 1][0] : '')).toUpperCase()
}
export const pct = (v: number, digits = 0) => `${(v * 100).toFixed(digits)}%`
export const plural = (n: number, one: string, many = one + 's') => `${n.toLocaleString('en-IN')} ${n === 1 ? one : many}`
/** Period label for the trend axis: day "9 Nov", week "Week of 3 Nov", month "Nov 2026". */
export function periodLabel(iso: string, grain: 'day' | 'week' | 'month', short = false): string {
  const d = new Date(iso + 'T00:00:00')
  if (grain === 'month') return d.toLocaleDateString('en-IN', short ? { month: 'short' } : { month: 'short', year: 'numeric' })
  const s = d.toLocaleDateString('en-IN', { day: 'numeric', month: 'short' })
  return grain === 'week' && !short ? `Week of ${s}` : s
}

/** "200 g" / "1 kg" / "500 ml" / "1.5 L" for a pack size stored in kg or l; "-" when the product has no pack size. */
export function packLabel(size: number | null | undefined, unit: string | null | undefined): string {
  if (!size || !unit) return '-'
  if (unit === 'kg') return size < 1 ? `${fmtQty(size * 1000)} g` : `${fmtQty(size)} kg`
  if (unit === 'l') return size < 1 ? `${fmtQty(size * 1000)} ml` : `${fmtQty(size)} L`
  return `${fmtQty(size)} ${unit}`
}
