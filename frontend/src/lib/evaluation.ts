/* Types for eval/results/evaluation_summary.json and the pure functions that turn it into the rows the AI performance page draws.
   Nothing here invents a number: every figure is read from the summary or computed from it, and a figure that was never measured stays null. */
import type { Latency } from '../types'

export interface EvalLanguage { key: string; name: string; native: string }
export interface EvalDataset { id: string; name: string; n: number; n_order: number; languages: string[]; provenance: string; file: string }
export interface SentenceRow { lang: string; dataset: string; dataset_label: string; n: number; exact: number; wrong: number; unrecognised: number; ambiguous: number; exact_pct: number | null }
export interface NameResolutionRow { lang: string; n: number; own: number; ambiguous_includes_own: number; wrong: number; none: number; missing: number; own_pct: number | null; applicable: boolean }
export interface BrandedVerdicts { exact: number; wrong_product: number; not_recognised: number; ambiguous_contains_expected: number }
export interface NoiseLevel {
  cer: number; line_precision: number; line_recall: number; line_f1: number; product_precision: number; product_recall: number; product_f1: number
  utterance_exact: number; utterance_exact_min: number; utterance_exact_max: number
}
export interface AblationPoint { cer: number; stage: string; label: string; utterance_exact: number; line_f1: number }
export interface TechRow { component: string; technology: string; purpose: string; status: string }
export interface HttpStat { n: number; p50_ms: number; p95_ms: number; max_ms: number; mean_ms: number }
/** Local HTTP timings written by scripts/benchmark_api.py: one machine, one server process, loopback, no Gnani calls. */
export interface ApiLatency { machine: string; note: string; n: number; [endpoint: string]: unknown }
export interface VerificationRow { category: string; total: number | null; passed: number | null; failed: number | null; skipped: number | null; status: string; how: string; ran: string }

export interface EvaluationSummary {
  schema: number
  generated_at: string
  app_version: string
  scope: string
  languages: EvalLanguage[]
  datasets: EvalDataset[]
  sentence_check: SentenceRow[]
  name_resolution: NameResolutionRow[]
  language_detection: { labels: string[]; matrix: number[][]; per_language: { lang: string; n: number; correct: number; pct: number }[]; n: number; note: string }
  branded: {
    verdicts: BrandedVerdicts; cases: number; exact_pct: number; wrong_product_pct: number; recognised_or_asked_pct: number
    by_language: Record<string, Partial<BrandedVerdicts>>
    confusion: { labels_rows: string[]; labels_cols: string[]; matrix: number[][]; wrong_pairs: { expected: string; got: string; count: number }[] }
    caveats: string[]
  }
  behaviour_checks: Record<string, string>
  noise: { seeds: number; n_sentences: number; levels: NoiseLevel[]; ablation: AblationPoint[]; note: string }
  end_to_end: {
    n_sentences: number; n_scored?: number; outcomes: Record<string, number>; by_language: Record<string, Record<string, number>>
    order_correct_pct: number | null; wrong_order_pct: number | null
    not_completed: unknown[]; clarifications: unknown[]
    stock_guard: Record<string, number>; note: string
  }
  parser_latency: { n: number; p50_ms: number; p95_ms: number; max_ms: number }
  technology?: TechRow[]
  limitations: string[]
}

export interface EvaluationResponse {
  available: boolean
  summary: EvaluationSummary | null
  file_modified?: string
  how_to_create: string
  verification?: { generated_at: string; rows: VerificationRow[] } | null
  api_latency?: ApiLatency | null
}

const HTTP_ENDPOINTS: [string, string][] = [
  ['text_turn', 'Order desk, one turn'], ['confirm_order_with_stock_update', 'Confirm an order and take stock'], ['inventory_list', 'Product list'],
  ['orders_page_20', 'Orders page, 20 rows'], ['analytics_overview_30d', 'Analytics overview, 30 days'], ['analytics_stock_movement_30d', 'Stock movement, 30 days'],
  ['catalogue_search', 'Catalogue search'], ['global_search', 'Search everything'], ['evaluation_summary', 'This page\'s results file'],
]

/** The endpoints worth showing, only those present in the file and carrying real numbers. */
export function httpRows(a: ApiLatency | null | undefined): { endpoint: string; label: string; stat: HttpStat }[] {
  if (!a) return []
  const out: { endpoint: string; label: string; stat: HttpStat }[] = []
  for (const [key, label] of HTTP_ENDPOINTS) {
    const v = a[key] as Partial<HttpStat> | undefined
    if (v && typeof v.p50_ms === 'number' && typeof v.p95_ms === 'number' && typeof v.n === 'number') out.push({ endpoint: key, label, stat: v as HttpStat })
  }
  return out
}

export const DATASET_ORDER = ['handwritten', 'templated', 'authored', 'branded'] as const

/** A percentage of a count, or null when there is nothing to divide by. Never 0% for "no data". */
export const ratio = (num: number, den: number): number | null => (den > 0 ? (100 * num) / den : null)
export const fmtPct = (v: number | null | undefined, digits = 1): string => (v === null || v === undefined ? 'n/a' : `${v.toFixed(digits)}%`)

/* ------------------------------------------------------------------------------------------ Table C: language evaluation */
export interface LanguageEvalRow { lang: string; name: string; samples: number; exact: number; wrong: number; unrecognised: number; ambiguous: number; exact_pct: number | null }

/** Per-language sentence results. `dataset` = 'all' adds every set together, 'written' adds the sets the project's author wrote (everything except the held-out
 *  branded products), otherwise it is one set's id. Languages with no sentences in the chosen set are left out. */
export function languageRows(s: EvaluationSummary, dataset: string = 'all'): LanguageEvalRow[] {
  const nameOf = (k: string) => s.languages.find((l) => l.key === k)?.name ?? k
  const inSet = (id: string) => dataset === 'all' || (dataset === 'written' ? id !== 'branded' : id === dataset)
  return s.languages.flatMap((l) => {
    const rows = s.sentence_check.filter((r) => r.lang === l.key && inSet(r.dataset))
    const n = rows.reduce((a, r) => a + r.n, 0)
    if (!n) return []
    const sum = (f: (r: SentenceRow) => number) => rows.reduce((a, r) => a + f(r), 0)
    const exact = sum((r) => r.exact)
    return [{ lang: l.key, name: nameOf(l.key), samples: n, exact, wrong: sum((r) => r.wrong), unrecognised: sum((r) => r.unrecognised), ambiguous: sum((r) => r.ambiguous), exact_pct: ratio(exact, n) }]
  })
}

/* ------------------------------------------------------------------------------------------ heatmap: language x metric */
export interface HeatCell { value: number | null; n: number; text: string; detail: string }
export interface HeatRow { lang: string; name: string; cells: HeatCell[] }
export const HEAT_COLUMNS = [
  { key: 'sentences', label: 'Written sentences', note: 'Exact match of the parsed order against the gold lines, on the handwritten, templated and authored sentences the project\'s author wrote' },
  { key: 'names', label: 'Name lookup', note: 'The product\'s own name resolves to that product (not applicable to Hinglish, which has no names of its own)' },
  { key: 'detect', label: 'Language label', note: 'Language the parser labels a sentence with when no language is selected' },
  { key: 'branded', label: 'Held-out brands', note: 'Exact match on synthetic sentences built from held-out product names (four languages only)' },
  { key: 'e2e', label: 'Order end to end', note: 'Typed sentence through the dialogue to a confirmed order with the right lines' },
] as const

export function heatmap(s: EvaluationSummary): HeatRow[] {
  return s.languages.map((l) => {
    const sent = languageRows(s, 'written').find((r) => r.lang === l.key)
    const nr = s.name_resolution.find((r) => r.lang === l.key)
    const det = s.language_detection.per_language.find((r) => r.lang === l.key)
    const bv = s.branded.by_language[l.key]
    const bn = bv ? Object.values(bv).reduce((a, v) => a + (v ?? 0), 0) : 0
    const e2e = s.end_to_end.by_language[l.key]
    const e2eScored = e2e ? Object.entries(e2e).filter(([k]) => !k.startsWith('skipped')).reduce((a, [, v]) => a + v, 0) : 0
    const cell = (value: number | null, n: number, num: number): HeatCell => ({ value, n, text: fmtPct(value), detail: value === null ? 'Not measured for this language' : `${num} of ${n}` })
    return {
      lang: l.key, name: l.name,
      cells: [
        cell(sent?.exact_pct ?? null, sent?.samples ?? 0, sent?.exact ?? 0),
        cell(nr && nr.applicable ? nr.own_pct : null, nr?.n ?? 0, nr?.own ?? 0),
        cell(det ? det.pct : null, det?.n ?? 0, det?.correct ?? 0),
        cell(bn ? ratio(bv?.exact ?? 0, bn) : null, bn, bv?.exact ?? 0),
        cell(e2eScored ? ratio(e2e?.order_correct ?? 0, e2eScored) : null, e2eScored, e2e?.order_correct ?? 0),
      ],
    }
  })
}

/* ------------------------------------------------------------------------------------------ error distribution */
export interface ErrorRow { lang: string; name: string; exact: number; asked: number; notRecognised: number; wrong: number; total: number }
/** How the held-out branded sentences ended, per language. 'asked' = the assistant asked which product (the right one was among its options). */
export function errorDistribution(s: EvaluationSummary): ErrorRow[] {
  return s.languages.flatMap((l) => {
    const v = s.branded.by_language[l.key]
    if (!v) return []
    const row = { exact: v.exact ?? 0, asked: v.ambiguous_contains_expected ?? 0, notRecognised: v.not_recognised ?? 0, wrong: v.wrong_product ?? 0 }
    return [{ lang: l.key, name: l.name, ...row, total: row.exact + row.asked + row.notRecognised + row.wrong }]
  })
}

/* ------------------------------------------------------------------------------------------ Table D: AI evaluation metrics */
export interface MetricRow { metric: string; result: string; dataset: string; method: string; interpretation: string; measured: 'text' | 'live' | 'not measured' }

export function metricRows(s: EvaluationSummary, latency: Latency | null, http?: ApiLatency | null): MetricRow[] {
  const b = s.branded
  const v = b.verdicts
  const rows: MetricRow[] = []
  const sentTotal = (id: string) => {
    const r = s.sentence_check.filter((x) => x.dataset === id)
    return { n: r.reduce((a, x) => a + x.n, 0), exact: r.reduce((a, x) => a + x.exact, 0) }
  }
  for (const d of s.datasets.filter((x) => x.id !== 'branded')) {
    const t = sentTotal(d.id)
    rows.push({
      metric: `Exact order match, ${d.name.toLowerCase()}`, result: `${fmtPct(ratio(t.exact, t.n))} (${t.exact} of ${t.n})`, dataset: `${d.name} (${d.n} sentences)`,
      method: 'Parse each sentence; every line (product, quantity, unit) must equal the gold lines',
      interpretation: d.id === 'authored' ? 'Shows the parser agrees with the sentences its author wrote, in all 11 languages; not an independent test' : 'Written by the parser\'s author, so this is a ceiling rather than a forecast', measured: 'text',
    })
  }
  rows.push(
    { metric: 'Held-out brands: exact product', result: `${fmtPct(b.exact_pct)} (${v.exact} of ${b.cases})`, dataset: 'Held-out branded products (synthetic sentences, real names)', method: 'Parse each sentence against a shop that holds the held-out products; the single product returned must be the expected one', interpretation: 'Optimistic: sentences are built from the product name itself and never name a pack size', measured: 'text' },
    { metric: 'Held-out brands: wrong product', result: `${fmtPct(b.wrong_product_pct)} (${v.wrong_product} of ${b.cases})`, dataset: 'Held-out branded products', method: 'One product returned and it is not the expected one', interpretation: 'The costly error: the shop would be handed the wrong item. Listed pair by pair in the confusion table', measured: 'text' },
    { metric: 'Held-out brands: asked which product', result: `${fmtPct(ratio(v.ambiguous_contains_expected, b.cases))} (${v.ambiguous_contains_expected} of ${b.cases})`, dataset: 'Held-out branded products', method: 'Several products returned and the expected one is among them; the dialogue then asks the customer', interpretation: 'Correct behaviour when a brand has several packs: ask instead of guessing', measured: 'text' },
    { metric: 'Held-out brands: not recognised', result: `${fmtPct(ratio(v.not_recognised, b.cases))} (${v.not_recognised} of ${b.cases})`, dataset: 'Held-out branded products', method: 'No product returned', interpretation: 'Safe failure: the assistant says it did not understand rather than adding a wrong item', measured: 'text' },
  )
  const det = s.language_detection
  const detOk = det.per_language.reduce((a, r) => a + r.correct, 0)
  rows.push({ metric: 'Language label without a selector', result: `${fmtPct(ratio(detOk, det.n))} (${detOk} of ${det.n})`, dataset: 'All sentence sets', method: 'Label chosen by the parser with no language selected, compared with the true language', interpretation: 'Hindi and Marathi share a script and English and Hinglish share letters, so the language selector settles those in the app', measured: 'text' })
  const lv = s.noise.levels
  const at = (cer: number) => lv.find((l) => Math.abs(l.cer - cer) < 1e-9)
  for (const cer of [0.03, 0.06, 0.1]) {
    const l = at(cer)
    if (!l) continue
    rows.push({
      metric: `Noise ${Math.round(cer * 100)}%: whole sentence exact`, result: `${fmtPct(100 * l.utterance_exact)} (range ${fmtPct(100 * l.utterance_exact_min, 0)}–${fmtPct(100 * l.utterance_exact_max, 0)})`,
      dataset: `Handwritten sentences, ${s.noise.n_sentences} order sentences x ${s.noise.seeds} random seeds`, method: 'Random letter damage at that rate; whole order must still equal the gold lines',
      interpretation: 'Simulated typing damage, not speech-recognition errors', measured: 'text',
    })
    rows.push({
      metric: `Noise ${Math.round(cer * 100)}%: order lines F1`, result: `${l.line_f1.toFixed(3)} (precision ${l.line_precision.toFixed(3)}, recall ${l.line_recall.toFixed(3)})`,
      dataset: 'Same noisy sentences', method: 'A predicted line counts only if product, quantity and unit are all right', interpretation: 'Precision above recall means errors are mostly missed lines, not invented ones', measured: 'text',
    })
  }
  const e = s.end_to_end
  const scored = e.n_scored ?? e.n_sentences
  rows.push({ metric: 'Typed order end to end', result: `${e.outcomes.order_correct ?? 0} of ${scored} orders correct, ${e.outcomes.order_wrong ?? 0} wrong`, dataset: `All ${e.n_sentences} sentences, 11 languages`, method: 'Sentence, "that\'s all" and "confirm" through the real dialogue against a throw-away shop with ample stock; the stored order lines must equal the gold', interpretation: `Same author-written sentences as above, so also a ceiling. ${e.n_sentences - scored} sentences with gold that cannot be written as an order are not scored`, measured: 'text' })
  const g = e.stock_guard
  rows.push({ metric: 'Stock guard, shelf empty', result: `${g.empty_refused ?? 0} of ${g.empty_checked ?? 0} refused, ${g.empty_negative_stock ?? 0} negative stock`, dataset: 'Orders from the end-to-end set', method: 'Same orders with every needed item at zero stock', interpretation: 'No order may be created and stock must never go below zero', measured: 'text' })
  rows.push({ metric: 'Stock guard, half the quantity', result: `${g.half_asked_or_offered ?? 0} asked or offered, ${g.half_refused ?? 0} refused, ${g.half_negative_stock ?? 0} over-stock orders`, dataset: 'Orders from the end-to-end set', method: 'Same orders with half the needed quantity on the shelf', interpretation: 'The assistant offers what is left instead of overselling', measured: 'text' })
  rows.push({ metric: 'Parser time per sentence', result: `p50 ${s.parser_latency.p50_ms} ms, p95 ${s.parser_latency.p95_ms} ms`, dataset: `Handwritten sentences x 5 passes (${s.parser_latency.n} timings)`, method: 'Wall-clock time of the parser alone, on the machine that built this file', interpretation: 'Text parsing only. Excludes speech recognition, speech synthesis and the network', measured: 'text' })
  const turn = httpRows(http).find((r) => r.endpoint === 'text_turn')
  if (turn && http) {
    rows.push({ metric: 'Server response time, one order turn', result: `p50 ${turn.stat.p50_ms} ms, p95 ${turn.stat.p95_ms} ms`, dataset: `${turn.stat.n} requests to a local server (${http.machine})`, method: 'Round trip of POST /api/text/turn over loopback HTTP, signed in, on a throw-away database (scripts/benchmark_api.py)', interpretation: 'One machine, one process, no network and no Gnani call. It shows the server is not the slow part, not what a shop will see', measured: 'text' })
  }
  const live = (key: 'gnani-stt' | 'gnani-tts', label: string, what: string): MetricRow => {
    const p = latency?.[key]
    const measured = !!p && p.ok > 0 && p.p50_ms !== null
    return {
      metric: label, result: measured ? `p50 ${Math.round(p!.p50_ms!)} ms, p95 ${p!.p95_ms === null ? 'n/a' : Math.round(p!.p95_ms) + ' ms'} (${p!.ok} calls)` : 'Not measured',
      dataset: measured ? 'Live calls made from this installation' : 'None', method: `Time of each real call to Gnani ${what}, recorded by the server`,
      interpretation: measured ? 'Depends on this network and on Gnani\'s service at the time' : 'No live call has been made, so there is nothing to report. Add a key in Settings and use the voice desk', measured: measured ? 'live' : 'not measured',
    }
  }
  rows.push(live('gnani-stt', 'Speech recognition time (Gnani Prisma)', 'speech recognition'), live('gnani-tts', 'Speech synthesis time (Gnani Timbre)', 'speech synthesis'))
  rows.push({ metric: 'Word error rate of speech recognition', result: 'Not measured', dataset: 'None', method: 'Would need recorded speech with reference transcripts and live Gnani calls', interpretation: 'No such recordings or calls exist in this project, so no figure is given', measured: 'not measured' })
  return rows
}

/* ------------------------------------------------------------------------------------------ headline figures */
export function headline(s: EvaluationSummary) {
  const v = s.branded.verdicts
  const e = s.end_to_end
  const scored = e.n_scored ?? e.n_sentences
  return {
    brandedExact: { pct: s.branded.exact_pct, n: v.exact, of: s.branded.cases },
    brandedWrong: { pct: s.branded.wrong_product_pct, n: v.wrong_product, of: s.branded.cases },
    brandedAsked: { n: v.ambiguous_contains_expected, notRecognised: v.not_recognised, of: s.branded.cases },
    orders: { correct: e.outcomes.order_correct ?? 0, wrong: e.outcomes.order_wrong ?? 0, scored },
  }
}

/** Sequential colour step 0..1 -> a mix of the brand gold into the card surface. Text on it is always the ink colour. */
export const heatColor = (t: number): string => `color-mix(in srgb, var(--gold) ${Math.round(8 + Math.max(0, Math.min(1, t)) * 84)}%, var(--surface))`
