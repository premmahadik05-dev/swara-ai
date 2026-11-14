import { describe, expect, it } from 'vitest'
import { DEFAULT_STT, LANG_KEYS, LANG_META, htmlLang, htmlLangOf, isLang, langName, langNative, liveSummary, understandingNote } from './languages'
import { LANG_LATIN, LANG_NAME, itemName, unitLabel } from './format'
import { languageInfo } from '../test/fixtures'
import type { CheckResult, LanguageInfo } from '../types'

const v = (over: Partial<LanguageInfo['verification']> = {}): LanguageInfo['verification'] => ({
  tts: { status: 'not_run' }, stt_code: { status: 'not_run' }, stt_loopback: { status: 'not_run' }, stt_human: { status: 'not_run' }, ...over,
})
const ok: CheckResult = { status: 'passed' }

describe('language table', () => {
  it('lists the eleven languages once each, the four original ones first', () => {
    expect(LANG_KEYS).toEqual(['gu', 'hi', 'en', 'hinglish', 'mr', 'bn', 'ta', 'te', 'kn', 'ml', 'pa'])
    expect(new Set(LANG_KEYS).size).toBe(11)
    expect(LANG_META.filter((l) => l.origin === 'original').map((l) => l.key)).toEqual(['gu', 'hi', 'en', 'hinglish'])
    expect(DEFAULT_STT).toBe('gu')
  })
  it('names each language in English and in its own script', () => {
    expect(langName('ta')).toBe('Tamil')
    expect(langNative('ta')).toBe('தமிழ்')
    expect(langNative('pa')).toBe('ਪੰਜਾਬੀ')
    expect(langName('xx')).toBe('xx')
    expect(langName(null)).toBe('')
    expect(isLang('ml')).toBe(true)
    expect(isLang('GU')).toBe(false)
    expect(isLang(undefined)).toBe(false)
  })
  it('gives each script the right lang attribute so the right font is used', () => {
    expect(htmlLang('bn')).toBe('bn')
    expect(htmlLang('hinglish')).toBe('hi-Latn')
    expect(htmlLang(undefined)).toBe('en')
    const samples: [string, string][] = [['ગુજરાતી', 'gu'], ['বাংলা', 'bn'], ['ਪੰਜਾਬੀ', 'pa'], ['தமிழ்', 'ta'], ['తెలుగు', 'te'], ['ಕನ್ನಡ', 'kn'], ['മലയാളം', 'ml'], ['हिन्दी', 'hi'], ['hello', 'en']]
    for (const [text, lang] of samples) expect(htmlLangOf(text)).toBe(lang)
  })
  it('keeps the names used by badges and filters in step with the table', () => {
    for (const l of LANG_META) { expect(LANG_LATIN[l.key]).toBe(l.name); expect(LANG_NAME[l.key]).toBe(l.native) }
  })
})

describe('liveSummary: never says "working" without a real pass', () => {
  it('says nothing has been checked when no run exists, and when the file is missing', () => {
    expect(liveSummary(v()).state).toBe('none')
    expect(liveSummary(v()).label).toBe('Not verified live')
    expect(liveSummary(undefined).state).toBe('none')
  })
  it('needs both a voice pass and a speech pass before saying "Live checked"', () => {
    expect(liveSummary(v({ tts: ok })).state).toBe('partial')
    expect(liveSummary(v({ stt_code: ok })).state).toBe('partial')
    const both = liveSummary(v({ tts: ok, stt_loopback: ok }))
    expect(both.state).toBe('verified')
    expect(both.label).toBe('Live checked')
    expect(both.detail).toMatch(/No recording of a person has been tested/)
  })
  it('only mentions a person\'s recording when one really passed', () => {
    const withPerson = liveSummary(v({ tts: ok, stt_human: ok }))
    expect(withPerson.state).toBe('verified')
    expect(withPerson.label).toMatch(/person/)
    expect(withPerson.detail).not.toMatch(/No recording of a person/)
  })
  it('shows a failure even when other checks passed, and names what failed', () => {
    const s = liveSummary(v({ tts: ok, stt_code: { status: 'failed', error_code: 'GNANI_400' } }))
    expect(s.state).toBe('failed')
    expect(s.detail).toMatch(/language code/)
    expect(s.detail).toMatch(/Passed: voice/)
  })
  it('never counts a simulated run as a pass', () => {
    const s = liveSummary(v({ tts: { status: 'simulated' }, stt_loopback: { status: 'simulated' } }))
    expect(s.state).toBe('simulated')
    expect(s.label).toBe('Simulated only')
  })
  it('skipped checks do not count as passes', () => {
    expect(liveSummary(v({ tts: { status: 'skipped' }, stt_code: { status: 'skipped' } })).state).toBe('none')
  })
})

describe('understandingNote', () => {
  it('says the seven new languages were not reviewed by a native speaker', () => {
    const t = understandingNote(languageInfo('ta'))
    expect(t).toMatch(/native speaker has not reviewed/)
    expect(t).toMatch(/not been checked against real speech/)
  })
  it('does not say that about the four languages that have been in use since the first release', () => {
    expect(understandingNote(languageInfo('gu'))).toMatch(/in use and tested/)
    expect(understandingNote(languageInfo('gu'))).not.toMatch(/native speaker/)
  })
})

describe('units and product names in the new languages', () => {
  it('has a unit word for every language, for every unit', () => {
    for (const unit of ['kg', 'l', 'pack', 'pc', 'g', 'dozen']) for (const l of LANG_KEYS) expect(unitLabel(unit, l), `${unit}/${l}`).not.toBe('')
    expect(unitLabel('kg', 'bn')).toBe('কেজি')
    expect(unitLabel('l', 'ta')).toBe('லிட்டர்')
  })
  it('uses the product name in the bill language when one exists and English when it does not', () => {
    const p = { name_en: 'Sugar', name_gu: 'ખાંડ', name_hi: 'चीनी', names: { mr: 'साखर', ta: 'சர்க்கரை' } }
    expect(itemName(p, 'mr')).toBe('साखर')
    expect(itemName(p, 'ta')).toBe('சர்க்கரை')
    expect(itemName(p, 'ml')).toBe('Sugar')
    expect(itemName({ ...p, names: undefined }, 'bn')).toBe('Sugar')
  })
})
