import { describe, expect, it } from 'vitest'
import shipped from '../../../eval/results/evaluation_summary.json?raw'
import { evaluationSummary } from '../test/fixtures'
import type { Latency } from '../types'
import { errorDistribution, fmtPct, headline, heatColor, heatmap, languageRows, metricRows, ratio, type EvaluationSummary } from './evaluation'

const live = (stt: Partial<Latency['gnani-stt']> = {}): Latency => ({
  'gnani-stt': { calls: 0, ok: 0, errors: 0, p50_ms: null, p95_ms: null, last_error: null, ...stt },
  'gnani-tts': { calls: 0, ok: 0, errors: 0, p50_ms: null, p95_ms: null, last_error: null },
  evon: { calls: 0, ok: 0, errors: 0, p50_ms: null, p95_ms: null, last_error: null },
  nlu: { turns: 0, p50_ms: null, p95_ms: null },
})

describe('evaluation helpers', () => {
  it('never turns "no data" into 0%', () => {
    expect(ratio(0, 0)).toBeNull()
    expect(ratio(1, 4)).toBe(25)
    expect(fmtPct(null)).toBe('n/a')
    expect(fmtPct(81.25)).toBe('81.3%')
  })

  it('adds the sentence sets together per language, or picks one set', () => {
    const s = evaluationSummary()
    const all = languageRows(s)
    expect(all.map((r) => r.name)).toEqual(['Gujarati', 'Hindi', 'Marathi'])
    expect(all[0]).toMatchObject({ samples: 17, exact: 16, wrong: 1, exact_pct: (100 * 16) / 17 })
    expect(languageRows(s, 'written')[0]).toMatchObject({ samples: 12, exact: 12, exact_pct: 100 })   // Gujarati without its 5 held-out brand sentences
    expect(languageRows(s, 'written').find((r) => r.lang === 'hi')).toMatchObject({ samples: 10, exact: 8, wrong: 1, unrecognised: 1 })
    expect(languageRows(s, 'branded').map((r) => r.lang)).toEqual(['gu', 'hi'])   // Marathi has no held-out sentences, so it is left out rather than shown as 0%
    expect(languageRows(s, 'authored').find((r) => r.lang === 'mr')).toMatchObject({ samples: 3, exact: 3 })
  })

  it('builds the language by metric heatmap and marks what was not measured', () => {
    const rows = heatmap(evaluationSummary())
    const mr = rows.find((r) => r.lang === 'mr')!
    expect(mr.cells.map((c) => c.text)).toEqual(['100.0%', 'n/a', '71.4%', 'n/a', '100.0%'])   // no name lookup, no held-out brands for Marathi
    expect(mr.cells[1]).toMatchObject({ value: null })
    expect(mr.cells[3].detail).toBe('Not measured for this language')
    const hi = rows.find((r) => r.lang === 'hi')!
    expect(hi.cells[0]).toMatchObject({ value: 80, n: 10 })   // 8 of the 10 handwritten + authored sentences
    expect(hi.cells[3]).toMatchObject({ value: 60, n: 5 })   // 3 exact of 3 + 1 + 1
    expect(hi.cells[4]).toMatchObject({ n: 4, text: '100.0%' })   // the 2 skipped sentences are not in the denominator
  })

  it('counts every held-out sentence in exactly one error bucket', () => {
    const s = evaluationSummary()
    const rows = errorDistribution(s)
    expect(rows.reduce((a, r) => a + r.total, 0)).toBe(s.branded.cases)
    expect(rows.find((r) => r.lang === 'hi')).toMatchObject({ exact: 3, asked: 1, notRecognised: 1, wrong: 0 })
  })

  it('states the headline figures with their denominators', () => {
    const h = headline(evaluationSummary())
    expect(h.brandedExact).toEqual({ pct: 70, n: 7, of: 10 })
    expect(h.orders).toEqual({ correct: 10, wrong: 0, scored: 10 })
  })

  it('lists speech recognition time and word error rate as NOT measured when no live call exists', () => {
    const rows = metricRows(evaluationSummary(), live())
    const stt = rows.find((r) => r.metric.startsWith('Speech recognition time'))!
    expect(stt).toMatchObject({ result: 'Not measured', measured: 'not measured', dataset: 'None' })
    expect(rows.find((r) => r.metric.startsWith('Word error rate'))).toMatchObject({ result: 'Not measured' })
    expect(rows.every((r) => r.result !== '' && r.interpretation !== '')).toBe(true)
  })

  it('reports speech recognition time only from real calls', () => {
    const rows = metricRows(evaluationSummary(), live({ calls: 6, ok: 5, errors: 1, p50_ms: 812.4, p95_ms: 1400 }))
    expect(rows.find((r) => r.metric.startsWith('Speech recognition time'))).toMatchObject({ result: 'p50 812 ms, p95 1400 ms (5 calls)', measured: 'live' })
    expect(metricRows(evaluationSummary(), live({ calls: 2, ok: 0, errors: 2 })).find((r) => r.metric.startsWith('Speech recognition time'))!.measured).toBe('not measured')
  })

  it('computes each result from the summary rather than from fixed text', () => {
    const rows = metricRows(evaluationSummary(), null)
    expect(rows.find((r) => r.metric === 'Held-out brands: exact product')!.result).toBe('70.0% (7 of 10)')
    expect(rows.find((r) => r.metric === 'Held-out brands: wrong product')!.result).toBe('10.0% (1 of 10)')
    expect(rows.find((r) => r.metric === 'Noise 6%: whole sentence exact')!.result).toContain('63.3%')
    expect(rows.find((r) => r.metric === 'Stock guard, shelf empty')!.result).toBe('10 of 10 refused, 0 negative stock')
    expect(rows.find((r) => r.metric === 'Typed order end to end')!.result).toBe('10 of 10 orders correct, 0 wrong')
  })

  it('keeps the heat colour on the gold ramp and inside the card surface range', () => {
    expect(heatColor(0)).toContain('var(--gold) 8%')
    expect(heatColor(1)).toContain('var(--gold) 92%')
    expect(heatColor(7)).toBe(heatColor(1))
    expect(heatColor(-3)).toBe(heatColor(0))
  })
})

describe('the shipped evaluation_summary.json', () => {
  const s = JSON.parse(shipped) as EvaluationSummary

  it('has the shape the page reads and adds up', () => {
    expect(s.languages).toHaveLength(11)
    expect(heatmap(s)).toHaveLength(11)
    for (const row of heatmap(s)) for (const c of row.cells) if (c.value !== null) { expect(c.value).toBeGreaterThanOrEqual(0); expect(c.value).toBeLessThanOrEqual(100) }
    const v = s.branded.verdicts
    expect(v.exact + v.wrong_product + v.not_recognised + v.ambiguous_contains_expected).toBe(s.branded.cases)
    expect(errorDistribution(s).reduce((a, r) => a + r.total, 0)).toBe(s.branded.cases)
    expect(s.branded.confusion.matrix.flat().reduce((a, n) => a + n, 0)).toBe(s.branded.cases)
    expect(s.language_detection.matrix.flat().reduce((a, n) => a + n, 0)).toBe(s.language_detection.n)
    expect(metricRows(s, null).length).toBeGreaterThan(15)
  })

  it('never claims a live or speech measurement', () => {
    expect(s.scope).toMatch(/^TEXT only/)
    const text = JSON.stringify(s)
    expect(text).not.toMatch(/verified live|(?<!not )live-verified|word error rate of \d/i)
    expect(s.technology?.filter((t) => /Gnani/.test(t.technology)).every((t) => /not live-verified/.test(t.status))).toBe(true)
  })
})
