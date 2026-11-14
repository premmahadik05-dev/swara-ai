import type { Lang, LanguageInfo, SttChoice } from '../types'

/**
 * What the screens need to name and draw a language without waiting for the server: its label in its own script, in English, and the
 * HTML `lang` code that picks the right font. The server's registry (GET /api/languages) stays the source of truth for what is switched
 * on, which voice is chosen and what has been verified; this table only covers names, so a screen that cannot reach the server still reads.
 */
export interface LangMeta { key: Lang; name: string; native: string; html: string; script: string; origin: 'original' | 'expansion' }

export const LANG_META: readonly LangMeta[] = [
  { key: 'gu', name: 'Gujarati', native: 'ગુજરાતી', html: 'gu', script: 'Gujarati', origin: 'original' },
  { key: 'hi', name: 'Hindi', native: 'हिन्दी', html: 'hi', script: 'Devanagari', origin: 'original' },
  { key: 'en', name: 'English', native: 'English', html: 'en', script: 'Latin', origin: 'original' },
  { key: 'hinglish', name: 'Hinglish', native: 'Hinglish', html: 'hi-Latn', script: 'Latin', origin: 'original' },
  { key: 'mr', name: 'Marathi', native: 'मराठी', html: 'mr', script: 'Devanagari', origin: 'expansion' },
  { key: 'bn', name: 'Bengali', native: 'বাংলা', html: 'bn', script: 'Bengali', origin: 'expansion' },
  { key: 'ta', name: 'Tamil', native: 'தமிழ்', html: 'ta', script: 'Tamil', origin: 'expansion' },
  { key: 'te', name: 'Telugu', native: 'తెలుగు', html: 'te', script: 'Telugu', origin: 'expansion' },
  { key: 'kn', name: 'Kannada', native: 'ಕನ್ನಡ', html: 'kn', script: 'Kannada', origin: 'expansion' },
  { key: 'ml', name: 'Malayalam', native: 'മലയാളം', html: 'ml', script: 'Malayalam', origin: 'expansion' },
  { key: 'pa', name: 'Punjabi', native: 'ਪੰਜਾਬੀ', html: 'pa', script: 'Gurmukhi', origin: 'expansion' },
]
export const LANG_KEYS: readonly Lang[] = LANG_META.map((l) => l.key)
const BY_KEY = new Map<string, LangMeta>(LANG_META.map((l) => [l.key, l]))

export const isLang = (v: unknown): v is Lang => typeof v === 'string' && BY_KEY.has(v)
/** English name ("Tamil"); an unknown key is shown as it is. */
export const langName = (key: string | null | undefined): string => (key ? (BY_KEY.get(key)?.name ?? key) : '')
/** Name in the language's own script ("தமிழ்"). */
export const langNative = (key: string | null | undefined): string => (key ? (BY_KEY.get(key)?.native ?? key) : '')
/** Value for the HTML `lang` attribute, so the browser picks the right font and hyphenation. */
export const htmlLang = (key: string | null | undefined): string => (key ? (BY_KEY.get(key)?.html ?? 'en') : 'en')
/** `lang` attribute for a piece of text in an unknown script, found from the characters themselves (sample sentences, typed text). */
export function htmlLangOf(text: string): string {
  if (/[઀-૿]/.test(text)) return 'gu'
  if (/[ঀ-৿]/.test(text)) return 'bn'
  if (/[਀-੿]/.test(text)) return 'pa'
  if (/[஀-௿]/.test(text)) return 'ta'
  if (/[ఀ-౿]/.test(text)) return 'te'
  if (/[ಀ-೿]/.test(text)) return 'kn'
  if (/[ഀ-ൿ]/.test(text)) return 'ml'
  if (/[ऀ-ॿ]/.test(text)) return 'hi'
  return 'en'
}

/** Quick pick for the language list: how much the live checks have shown. Never says "working" without a live pass. */
export type LiveState = 'verified' | 'partial' | 'failed' | 'simulated' | 'none'
export interface LiveSummary { state: LiveState; label: string; detail: string }

const CHECK_NAME: Record<string, string> = { tts: 'voice', stt_code: 'language code', stt_loopback: 'speech (synthetic loopback)', stt_human: 'speech (a person)' }

export function liveSummary(v: LanguageInfo['verification'] | undefined): LiveSummary {
  if (!v) return { state: 'none', label: 'Not verified live', detail: 'No live check has been run against Gnani for this language.' }
  const entries = Object.entries(v)
  const failed = entries.filter(([, c]) => c.status === 'failed').map(([k]) => CHECK_NAME[k] ?? k)
  const passed = entries.filter(([, c]) => c.status === 'passed').map(([k]) => CHECK_NAME[k] ?? k)
  if (entries.some(([, c]) => c.status === 'simulated')) return { state: 'simulated', label: 'Simulated only', detail: 'The results file for this language came from a simulated run, not from Gnani.' }
  if (failed.length) return { state: 'failed', label: 'Live check failed', detail: `Failed against Gnani: ${failed.join(', ')}.${passed.length ? ` Passed: ${passed.join(', ')}.` : ''}` }
  const voice = v.tts?.status === 'passed'
  const stt = v.stt_code?.status === 'passed' || v.stt_loopback?.status === 'passed' || v.stt_human?.status === 'passed'
  if (voice && stt) {
    const person = v.stt_human?.status === 'passed'
    return { state: 'verified', label: person ? 'Live checked, with a person\'s recording' : 'Live checked', detail: `Passed against Gnani: ${passed.join(', ')}.${person ? '' : ' No recording of a person has been tested.'}` }
  }
  if (passed.length) return { state: 'partial', label: 'Partly live checked', detail: `Passed: ${passed.join(', ')}. The other checks have not been run.` }
  return { state: 'none', label: 'Not verified live', detail: 'No live check has been run against Gnani for this language.' }
}

/** The honest one-line description of how far the understanding of a language can be trusted. */
export function understandingNote(l: Pick<LanguageInfo, 'name' | 'nlu_status'>): string {
  return l.nlu_status === 'tested'
    ? `Understanding for ${l.name} has been in use and tested since the first release.`
    : `Understanding for ${l.name} was written for this release and is unit-tested. A native speaker has not reviewed it, and it has not been checked against real speech output.`
}

export const DEFAULT_STT: SttChoice = 'gu'
