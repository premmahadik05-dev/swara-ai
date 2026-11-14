import type { CartLine, CheckResult, InvoiceData, LanguageInfo, LanguagesResponse, Lang, Overview, PaymentConfig, PaymentDetail, PublicSettings, TurnResponse } from '../types'
import { LANG_META } from '../lib/languages'

export const json = (body: unknown, status = 200): Response =>
  new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } })

export const RICE: CartLine = {
  product_id: 1, sku: 'RICE-BASMATI', name_en: 'Rice', name_gu: 'ચોખા', name_hi: 'चावल', qty: '2', unit: 'kg',
  unit_price_paise: 5800, line_total_paise: 11600, assumed: false, in_stock: 40,
}
export const MILK: CartLine = {
  product_id: 2, sku: 'MILK-1L', name_en: 'Milk', name_gu: 'દૂધ', name_hi: 'दूध', qty: '1', unit: 'l',
  unit_price_paise: 5600, line_total_paise: 5600, assumed: false, in_stock: 90,
}

export function turn(over: Partial<TurnResponse> = {}): TurnResponse {
  return {
    session_id: 's1', transcript: 'x', language: 'hinglish', reply_text: '2 kilo Rice add kar diya.', reply_lang: 'hinglish',
    phase: 'collecting', awaiting: 'more_items', pending: null,
    cart: { lines: [RICE, MILK], total_paise: 17200 },
    parse: { intent: 'add', language: 'hinglish', script: 'latin', normalized: 'x', cues: {}, lines: [] },
    events: [], order: null, low_stock_alerts: [], timings: { stt_ms: null, nlu_ms: 0.6, tts_ms: null }, audio: null, assistant_turn_id: 11,
    ...over,
  }
}

export function settings(over: Partial<PublicSettings['gnani']> = {}): PublicSettings {
  return {
    store_name: 'Patel Kirana (demo)', admin_protected: false,
    gnani: { configured: false, key_hint: null, base_url: 'https://api.vachana.ai', stt_model: 'prisma-v2.5', stt_format: 'verbatim', stt_bias: false, tts_model: 'timbre-v2.5', calls_last_hour: 0, max_calls_per_hour: 300, ...over },
    voices: {
      gu: 'Falak', hi: 'Nalini', en: 'Devika', hinglish: 'Poorvi', mr: 'Zahira', bn: 'Kirra', ta: 'Asmita', te: 'Lavanya', kn: 'Saanvi', ml: 'Reshma', pa: 'Mehuli',
      speed: 1,
      catalogue: { 'gu-IN': ['Falak', 'Veera'], 'hi-IN': ['Nalini'], 'en-IN': ['Devika'], 'hi-en': ['Poorvi'], 'mr-IN': ['Zahira', 'Ishaan'], 'bn-IN': ['Kirra', 'Dhruva'], 'ta-IN': ['Asmita'], 'te-IN': ['Lavanya', 'Lehara', 'Suhana', 'Varuni', 'Yukti'], 'kn-IN': ['Saanvi', 'Kavin'], 'ml-IN': ['Reshma', 'Riyaan'], 'pa-IN': ['Mehuli', 'Zayan'] },
    },
    languages: { disabled: [], env: 'DISABLED_LANGUAGES' },
    evon: { available_on_gnani_api: false, configured: false, note: 'Evon v3.3 is not exposed on the Gnani API.' },
    limits: { max_audio_seconds: 30, max_upload_mb: 8, rate_limit_per_minute: 60 },
    payments: paymentConfig(),
  } as PublicSettings
}

export function overview(): Overview {
  return {
    window_days: 30, include_synthetic: true,
    kpis: { revenue_paise: 26336700, orders: 712, avg_basket_paise: 36990, voice_share: 0.61, today_revenue_paise: 478000, today_orders: 8, low_stock_count: 9, out_of_stock_count: 2, cancelled: 29, non_synthetic_orders_total: 0 },
    sales_by_day: [{ date: '2026-11-08', revenue_paise: 900000, orders: 25 }, { date: '2026-11-09', revenue_paise: 1200000, orders: 31 }],
    top_products: [{ name: 'Milk', revenue_paise: 1700000, qty: 300, unit: 'l' }],
    category_mix: [{ category: 'Dairy & Bakery', revenue_paise: 3800000 }],
    orders_by_status: [{ status: 'confirmed', orders: 80 }, { status: 'fulfilled', orders: 632 }, { status: 'cancelled', orders: 29 }],
    orders_by_language: [{ language: 'gu', orders: 275 }, { language: 'hi', orders: 100 }],
    orders_by_channel: [{ channel: 'voice', orders: 437 }, { channel: 'text', orders: 275 }],
    orders_by_hour: Array.from({ length: 24 }, (_, h) => ({ hour: h, orders: h === 9 ? 80 : 0 })),
  } as Overview
}

import { vi } from 'vitest'
import type { DemandInsights, InventorySummary, SalesPoint, SalesSeries } from '../types'

/** A daily/weekly/monthly series of `n` periods. Every complete period is ₹1,000 over 10 orders; the last is in progress. */
export function salesSeries(grain: 'day' | 'week' | 'month' = 'day', n = 61, over: { cur?: number; prev?: number; partialOrders?: number; window?: number } = {}): SalesSeries {
  const per = over.window ?? (n - 1) / 2   // periods in the 'current' window; the rest of the complete ones count as 'previous'
  const series: SalesPoint[] = Array.from({ length: n }, (_, i) => {
    const last = i === n - 1
    const isCur = !last && i >= n - 1 - per
    const rev = last ? 30000 : isCur ? (over.cur ?? 100000) : (over.prev ?? 100000)
    const orders = last ? (over.partialOrders ?? 3) : 10
    const d = new Date(Date.UTC(2026, 10, 10) - (n - 1 - i) * 86400000)
    return { period: d.toISOString().slice(0, 10), revenue_paise: rev, orders, avg_basket_paise: Math.round(rev / orders), partial: last }
  })
  const revenue_paise = series.reduce((t, p) => t + p.revenue_paise, 0)
  const orders = series.reduce((t, p) => t + p.orders, 0)
  return { grain, periods: n, include_synthetic: true, series, totals: { revenue_paise, orders, avg_basket_paise: Math.round(revenue_paise / orders) } }
}

export function inventorySummary(): InventorySummary {
  return {
    products: 70, valuation_retail_paise: 18450000, valuation_cost_paise: null, products_with_cost: 0,
    price_basis: { demo: 65, shop: 5 },
    by_category: [{ category: 'Grains & Flour', retail_paise: 9000000, items: 12, units_low: 1 }, { category: 'Dairy & Bakery', retail_paise: 3000000, items: 9, units_low: 0 }],
    out_of_stock: [{ product_id: 7, name: 'Toor Dal', unit: 'kg', stock: 0, reorder_level: 10 }],
    low_stock: [{ product_id: 9, name: 'Sugar', unit: 'kg', stock: 3, reorder_level: 10 }],
    stock_health: { ok: 60, low: 9, out: 1 },
    no_sales: { days: 30, items: 2, retail_paise: 120000, top: [{ product_id: 11, name: 'Saffron 1g', retail_paise: 90000 }] },
  }
}

export function demand(): DemandInsights {
  const row = { product_id: 9, name: 'Sugar', category: 'Grains & Flour', unit: 'kg', units_sold: 90, revenue_paise: 405000, velocity_per_day: 3, stock: 3, days_of_cover: 1, trend_pct: 25, suggested_reorder_qty: 39, status: 'stockout_risk' as const }
  return { window_days: 30, include_synthetic: true, method: 'Trailing 30-day sales per day; days of cover = stock / that rate.', previous_window: { days: 30, days_with_orders: 28, comparable: true }, products: [row], stockout_risk: [row], rising: [row], falling: [] }
}

/**
 * Stub `fetch` with a table of "METHOD /path" -> body (or a function). Matches on path without the query string first, then with it.
 * Unknown routes fail the test loudly instead of returning something plausible.
 */
export function mockRoutes(routes: Record<string, unknown | ((url: URL, init: RequestInit) => unknown | Promise<unknown>)>) {
  const calls: { method: string; url: string; body: string | null }[] = []
  const f = vi.fn().mockImplementation(async (input: string, init: RequestInit = {}) => {
    const url = new URL(input, 'http://localhost')
    const method = (init.method ?? 'GET').toUpperCase()
    calls.push({ method, url: url.pathname + url.search, body: (init.body as string) ?? null })
    const hit = routes[`${method} ${url.pathname}${url.search}`] ?? routes[`${method} ${url.pathname}`]
    if (hit === undefined) throw new Error(`Unexpected request in test: ${method} ${url.pathname}${url.search}`)
    const out = typeof hit === 'function' ? await (hit as (u: URL, i: RequestInit) => unknown)(url, init) : hit
    return out instanceof Response ? out : json(out)
  })
  vi.stubGlobal('fetch', f)
  return { f, calls, urls: () => calls.map((c) => c.url) }
}

import type { EvaluationSummary } from '../lib/evaluation'
import type { Customer, Order, OrderList, StockMovementReport } from '../types'

export function order(over: Partial<Order> = {}): Order {
  return {
    id: 1, code: 'SW-0001', status: 'confirmed', channel: 'voice', language: 'gu', customer_name: 'Walk-in customer', customer_id: null,
    total_paise: 17200, is_synthetic: false, created_at: '2026-11-10T05:00:00Z', session_id: 'abcdef12-0000', 
    items: [{ product_id: 1, name: 'Rice', qty: '2', unit: 'kg', unit_price_paise: 6000, line_total_paise: 12000 }, { product_id: 2, name: 'Milk', qty: '1', unit: 'l', unit_price_paise: 5200, line_total_paise: 5200 }],
    ...over,
  } as Order
}
export function orderList(items: Order[] = [order(), order({ id: 2, code: 'SW-0002', status: 'fulfilled', channel: 'text', language: 'hi', is_synthetic: true, customer_name: 'Meena Patel', customer_id: 5 })], total = items.length): OrderList {
  return { total, limit: 20, offset: 0, counts: { all: total, confirmed: 1, fulfilled: 1, cancelled: 0 }, items }
}
export function customer(over: Partial<Customer> = {}): Customer {
  return {
    id: 5, name: 'Meena Patel', phone: '9876500001', language: 'gu', notes: '', is_synthetic: true, is_active: true, created_at: '2026-10-01T05:00:00Z',
    orders: 12, spent_paise: 540000, avg_basket_paise: 45000, last_order_at: '2026-11-09T05:00:00Z', ...over,
  }
}

import type { InventoryList, Product } from '../types'

export function product(over: Partial<Product> = {}): Product {
  return {
    id: 1, sku: 'RICE-BAS', name_en: 'Basmati Rice', name_gu: 'બાસમતી ચોખા', name_hi: 'बासमती चावल', category: 'Grains & Flour', unit: 'kg', price_paise: 9000,
    stock: 40, reorder_level: 10, pack_size: null, pack_size_unit: null, aliases: [], default_for: [], is_active: true, stock_status: 'ok', brand: '', ean: null,
    source: 'curated', source_ref: null, price_basis: 'demo', cost_paise: null, stock_value_paise: 360000, updated_at: '2026-11-10T05:00:00Z', ...over,
  }
}
export function inventoryList(items: Product[] = [product(), product({ id: 2, sku: 'SUGAR', name_en: 'Sugar', stock: 3, stock_status: 'low', price_basis: 'shop', stock_value_paise: 13500 }), product({ id: 3, sku: 'DAL', name_en: 'Toor Dal', stock: 0, stock_status: 'out', stock_value_paise: 0 })]): InventoryList {
  return { total: items.length, page: 1, page_size: 25, items, counts: { all: items.length, ok: 1, low: 1, out: 1 } }
}

/* ---- accounts ---- */
export const AUTH_CONFIG = {
  signup_open: true, has_owner: true, owner_email_set: false, email_configured: false, verification_required: false,
  password: { min_length: 10, max_length: 128 }, session: { hours: 12, idle_minutes: 120, remember_days: 30 },
}
export const USER = {
  id: 1, email: 'ramesh@example.com', full_name: 'Ramesh Patel', role: 'owner', email_verified: false,
  created_at: '2026-11-01T09:00:00Z', last_login_at: '2026-11-10T08:30:00Z', preferences: {},
}
export const err = (status: number, code: string, message: string, extra: object = {}) => json({ detail: { code, message, ...extra } }, status)

/** A CSV download response, the way the export endpoints answer. */
export const csvResponse = (text: string, filename = 'swara-export-20261110.csv', truncated = false): Response =>
  new Response('﻿' + text, {
    status: 200,
    headers: { 'Content-Type': 'text/csv; charset=utf-8', 'Content-Disposition': `attachment; filename="${filename}"`, ...(truncated ? { 'X-Export-Truncated': 'true' } : {}) },
  })

/** Stand-ins for the two browser features a download needs (jsdom has neither); returns what was saved. */
export function captureDownloads() {
  const saved: { filename: string; blob: Blob }[] = []
  const create = vi.fn((b: Blob) => { saved.push({ filename: '', blob: b }); return 'blob:swara-test' })
  const revoke = vi.fn()
  Object.assign(URL, { createObjectURL: create, revokeObjectURL: revoke })
  const click = vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(function (this: HTMLAnchorElement) {
    saved[saved.length - 1].filename = this.download
  })
  return { saved, restore: () => { click.mockRestore() } }
}


const CODES: Record<Lang, [string, string, string]> = {
  gu: ['gu-IN', 'gu-IN', 'Falak'], hi: ['hi-IN', 'hi-IN', 'Nalini'], en: ['en-IN', 'en-IN', 'Devika'], hinglish: ['en-IN', 'hi-en', 'Poorvi'],
  mr: ['mr-IN', 'mr-IN', 'Zahira'], bn: ['bn-IN', 'bn-IN', 'Kirra'], ta: ['ta-IN', 'ta-IN', 'Asmita'], te: ['te-IN', 'te-IN', 'Lavanya'],
  kn: ['kn-IN', 'kn-IN', 'Saanvi'], ml: ['ml-IN', 'ml-IN', 'Reshma'], pa: ['pa-IN', 'pa-IN', 'Mehuli'],
}
const NOT_RUN: CheckResult = { status: 'not_run' }

/** One row of GET /api/languages. Nothing has been verified live unless a test says so. */
export function languageInfo(key: Lang, over: Partial<LanguageInfo> = {}): LanguageInfo {
  const m = LANG_META.find((l) => l.key === key)!
  const [stt, tts, voice] = CODES[key]
  return {
    key, name: m.name, native: m.native, script: m.script, stt_code: stt, tts_code: tts, voice, default_voice: voice, voices: [voice],
    enabled: true, origin: m.origin, nlu_status: m.origin === 'original' ? 'tested' : 'authored', tts_depth: 'supported', stt_note: '',
    sample: key === 'en' ? 'two kilo rice and one litre milk' : 'sample', verification: { tts: NOT_RUN, stt_code: NOT_RUN, stt_loopback: NOT_RUN, stt_human: NOT_RUN }, ...over,
  }
}

export function languages(over: Partial<LanguagesResponse> = {}, rows?: LanguageInfo[]): LanguagesResponse {
  return {
    default: 'gu', stt_model: 'prisma-v2.5', tts_model: 'timbre-v2.5',
    modes: [
      { key: 'auto', name: 'Auto-detect', available: false, reason: 'Automatic language detection needs Prisma v3.0; this server uses prisma-v2.5.' },
      { key: 'mixed', name: 'Mixed languages', available: false, reason: 'Needs Prisma v3.0; this server uses prisma-v2.5.' },
    ],
    disabled: [], docs: { stt: 'https://docs.gnani.ai/stt', tts_voices: 'https://docs.gnani.ai/tts-voices', tts_text: 'https://docs.gnani.ai/tts', checked_on: '2026-11-10' },
    verification: { mode: 'none', generated_at: null, stt_model: null, tts_model: null },
    languages: rows ?? LANG_META.map((m) => languageInfo(m.key)), ...over,
  }
}

/** A stock-movement report for `days` days with two products that moved. Opening + added + returned - sold - written off = current for each row. */
export function stockMovement(over: Partial<StockMovementReport> = {}, days = 30): StockMovementReport {
  const t = new Date('2026-11-11T00:00:00Z')
  const series = Array.from({ length: days }, (_, i) => {
    const d = new Date(t.getTime() - (days - 1 - i) * 86400000).toISOString().slice(0, 10)
    return { date: d, in_paise: i === days - 1 ? 30000 : 0, out_paise: i === days - 2 ? 12000 : 0 }
  })
  return {
    window_days: days, movements: 3, products_moved: 2, products_total: 65,
    rows: [
      { product_id: 1, name: 'Basmati Rice', category: 'Grains', unit: 'kg', opening: 10, added: 5, returned: 0, sold: 6, written_off: 0, current: 9, reorder_level: 4, status: 'ok' },
      { product_id: 2, name: 'Toor Dal', category: 'Pulses', unit: 'kg', opening: 3, added: 0, returned: 1, sold: 3, written_off: 0, current: 1, reorder_level: 4, status: 'low' },
    ],
    truncated: false, series, totals: { in_paise: 30000, out_paise: 12000 },
    method: 'From the stock ledger: orders confirmed, cancelled or restocked in the app.', ...over,
  }
}

/** A small but complete evaluation summary: three languages (Hinglish is deliberately absent, so "not applicable" paths are not needed here) with figures that are easy to check by hand. */
export function evaluationSummary(over: Partial<EvaluationSummary> = {}): EvaluationSummary {
  return {
    schema: 1, generated_at: '2026-11-11T05:45:53+00:00', app_version: '2.5.0', scope: 'TEXT only. No speech recognition, no speech synthesis and no Gnani call is involved in any number in this file.',
    languages: [{ key: 'gu', name: 'Gujarati', native: 'ગુજરાતી' }, { key: 'hi', name: 'Hindi', native: 'हिन्दी' }, { key: 'mr', name: 'Marathi', native: 'मराठी' }],
    datasets: [
      { id: 'handwritten', name: 'Handwritten sentences', n: 20, n_order: 18, languages: ['gu', 'hi'], provenance: 'Written by the parser author', file: 'eval/utterances.jsonl' },
      { id: 'authored', name: 'Authored sentences, all 11 languages', n: 7, n_order: 7, languages: ['gu', 'hi', 'mr'], provenance: 'Authored with no native review', file: 'eval/language_sentences.jsonl' },
      { id: 'branded', name: 'Held-out branded products', n: 10, n_order: 10, languages: ['gu', 'hi'], provenance: 'Synthetic sentences, real names', file: 'data/test/branded_utterances.jsonl' },
    ],
    sentence_check: [
      { lang: 'gu', dataset: 'handwritten', dataset_label: 'Handwritten sentences', n: 10, exact: 10, wrong: 0, unrecognised: 0, ambiguous: 0, exact_pct: 100 },
      { lang: 'hi', dataset: 'handwritten', dataset_label: 'Handwritten sentences', n: 8, exact: 6, wrong: 1, unrecognised: 1, ambiguous: 0, exact_pct: 75 },
      { lang: 'gu', dataset: 'authored', dataset_label: 'Authored', n: 2, exact: 2, wrong: 0, unrecognised: 0, ambiguous: 0, exact_pct: 100 },
      { lang: 'hi', dataset: 'authored', dataset_label: 'Authored', n: 2, exact: 2, wrong: 0, unrecognised: 0, ambiguous: 0, exact_pct: 100 },
      { lang: 'mr', dataset: 'authored', dataset_label: 'Authored', n: 3, exact: 3, wrong: 0, unrecognised: 0, ambiguous: 0, exact_pct: 100 },
      { lang: 'gu', dataset: 'branded', dataset_label: 'Held-out', n: 5, exact: 4, wrong: 1, unrecognised: 0, ambiguous: 0, exact_pct: 80 },
      { lang: 'hi', dataset: 'branded', dataset_label: 'Held-out', n: 5, exact: 3, wrong: 0, unrecognised: 1, ambiguous: 1, exact_pct: 60 },
    ],
    name_resolution: [
      { lang: 'gu', n: 4, own: 4, ambiguous_includes_own: 0, wrong: 0, none: 0, missing: 0, own_pct: 100, applicable: true },
      { lang: 'hi', n: 4, own: 3, ambiguous_includes_own: 1, wrong: 0, none: 0, missing: 0, own_pct: 75, applicable: true },
      { lang: 'mr', n: 0, own: 0, ambiguous_includes_own: 0, wrong: 0, none: 0, missing: 0, own_pct: null, applicable: false },
    ],
    language_detection: {
      labels: ['gu', 'hi', 'mr'], matrix: [[10, 0, 0], [0, 12, 0], [0, 2, 5]],
      per_language: [{ lang: 'gu', n: 10, correct: 10, pct: 100 }, { lang: 'hi', n: 12, correct: 12, pct: 100 }, { lang: 'mr', n: 7, correct: 5, pct: 71.4 }],
      n: 29, note: 'Hindi and Marathi share a script.',
    },
    branded: {
      verdicts: { exact: 7, wrong_product: 1, not_recognised: 1, ambiguous_contains_expected: 1 }, cases: 10, exact_pct: 70, wrong_product_pct: 10, recognised_or_asked_pct: 80,
      by_language: { gu: { exact: 4, wrong_product: 1 }, hi: { exact: 3, not_recognised: 1, ambiguous_contains_expected: 1 } },
      confusion: {
        labels_rows: ['Snacks', 'Dairy'], labels_cols: ['Snacks', 'Dairy', 'Asked which pack', 'Not recognised'], matrix: [[4, 1, 0, 0], [0, 3, 1, 1]],
        wrong_pairs: [{ expected: 'Parle G', got: 'Parle-G 100 g', count: 1 }],
      },
      caveats: ['Sentences are templated from the product name, so this is an optimistic ceiling.'],
    },
    behaviour_checks: { ambiguous_not_guessed: '4/4', no_item_no_false_add: '10/10' },
    noise: {
      seeds: 5, n_sentences: 18,
      levels: [
        { cer: 0, line_precision: 1, line_recall: 1, line_f1: 1, product_precision: 1, product_recall: 1, product_f1: 1, utterance_exact: 1, utterance_exact_min: 1, utterance_exact_max: 1 },
        { cer: 0.06, line_precision: 0.8, line_recall: 0.6, line_f1: 0.686, product_precision: 0.9, product_recall: 0.8, product_f1: 0.847, utterance_exact: 0.6333, utterance_exact_min: 0.58, utterance_exact_max: 0.69 },
      ],
      ablation: [
        { cer: 0.06, stage: 'exact', label: 'Exact name or alias', utterance_exact: 0.5, line_f1: 0.6 },
        { cer: 0.06, stage: 'fuzzy', label: '+ fuzzy match (full system)', utterance_exact: 0.6333, line_f1: 0.686 },
      ],
      note: 'Simulated character damage, not acoustic noise.',
    },
    end_to_end: {
      n_sentences: 12, n_scored: 10, outcomes: { order_correct: 10, skipped_gold_not_convertible: 2 }, by_language: { gu: { order_correct: 5 }, hi: { order_correct: 4, skipped_gold_not_convertible: 2 }, mr: { order_correct: 1 } },
      order_correct_pct: 100, wrong_order_pct: 0, not_completed: [], clarifications: [],
      stock_guard: { empty_checked: 10, empty_negative_stock: 0, empty_refused: 10, half_checked: 10, half_negative_stock: 0, half_asked_or_offered: 9, half_refused: 1 },
      note: 'Typed text through the real dialogue.',
    },
    parser_latency: { n: 100, p50_ms: 0.14, p95_ms: 0.24, max_ms: 0.7 },
    technology: [
      { component: 'API server', technology: 'fastapi 0.162.2', purpose: 'REST API', status: 'Implemented and tested' },
      { component: 'Speech recognition', technology: 'Gnani Prisma v2.5', purpose: 'Speech to text', status: 'Implemented; tested with mocked HTTP, not live-verified' },
    ],
    limitations: ['The gold labels were written by the parser author, so 100% is a ceiling.', 'The added languages have had no native-speaker review.', 'No live call was made.'],
    ...over,
  }
}

const sum = (p50: number | null, n = 6): import('../types').StatSummary =>
  p50 === null ? { n: 0, p50: null, p95: null, max: null, mean: null } : { n, p50, p95: Math.round(p50 * 1.8), max: Math.round(p50 * 2.4), mean: Math.round(p50 * 1.1) }

/** GET /api/diagnostics/voice. Pass `empty: true` for a shop with no spoken orders yet. */
export function voiceDiagnostics(opts: { empty?: boolean } = {}): import('../types').VoiceDiagnostics {
  const e = !!opts.empty
  const stages = {
    validate_ms: sum(e ? null : 4), stt_ms: sum(e ? null : 900), nlu_ms: sum(e ? null : 6), db_ms: sum(e ? null : 3),
    process_ms: sum(e ? null : 12), tts_ms: sum(e ? null : 600), server_ms: sum(e ? null : 1530),
  }
  return {
    window_hours: 168, generated_at: '2026-11-11T05:00:00Z',
    voice: {
      turns: e ? 0 : 6, by_mode: e ? { voice: 0, stream: 0 } : { voice: 5, stream: 1 }, stages,
      stage_share_of_median: e ? { validate_ms: null, stt_ms: null, process_ms: null, tts_ms: null } : { validate_ms: 0.003, stt_ms: 0.59, process_ms: 0.008, tts_ms: 0.39 },
      tts_cached_share: e ? null : 0.17, retried_speech_calls: e ? 0 : 1,
    },
    browser_reported: {
      turns: e ? 0 : 4, end_to_reply_ms: sum(e ? null : 1400, 4), end_to_audio_ms: sum(e ? null : 2100, 4), capture_ms: sum(e ? null : 2600, 4),
      endpoints: e ? [] : [{ kind: 'auto', turns: 3 }, { kind: 'manual', turns: 1 }],
    },
    typed: { turns: e ? 0 : 9, process_ms: sum(e ? null : 11, 9) },
    gnani: {
      stt: { ...sum(e ? null : 880), calls: e ? 0 : 7, ok: e ? 0 : 6, errors: e ? 0 : 1, retried: e ? 0 : 1, error_types: e ? [] : [{ type: 'ReadTimeout', count: 1 }] },
      tts: { ...sum(e ? null : 590), calls: e ? 0 : 5, ok: e ? 0 : 5, errors: 0, retried: 0, error_types: [] },
    },
    budget: { calls_last_hour: e ? 0 : 3, max_per_hour: 600 },
    config: { stt_model: 'prisma-v2.5', tts_model: 'timbre-v2.5', stt_timeout_s: 20, tts_timeout_s: 15, connect_timeout_s: 5, tts_sample_rate: 22050, tts_speed: 1, gnani_configured: !e },
    slowest: e ? [] : [
      { turn_id: 41, at: '2026-11-10T11:00:00Z', mode: 'voice', language: 'gu', server_ms: 3100, validate_ms: 5, stt_ms: 2300, process_ms: 14, tts_ms: 780, tts_cached: false, stt_attempts: 2, end_to_reply_ms: 3500 },
      { turn_id: 38, at: '2026-11-10T10:00:00Z', mode: 'stream', language: 'hi', server_ms: 1600, validate_ms: 4, stt_ms: 920, process_ms: 10, tts_ms: null, tts_cached: true, stt_attempts: 1, end_to_reply_ms: null },
    ],
  }
}


/** Payments as the owner sees them with nothing set up: cash works, UPI and Razorpay say what is missing. */
export function paymentConfig(over: { razorpay?: boolean; vpa?: string; owner?: boolean; qr?: boolean } = {}): PaymentConfig {
  const rz = !!over.razorpay
  const upi = !!over.vpa || (rz && !!over.qr)
  return {
    mode: 'test', currency: 'INR', gst_configured: false, pending_minutes: 30,
    methods: {
      cash: { available: true, reason: null },
      upi: { available: upi, mode: rz && over.qr ? 'provider' : over.vpa ? 'manual' : null, reason: upi ? null : "Add the shop's UPI ID in Settings to show a UPI QR code." },
      razorpay: { available: rz, reason: rz ? null : 'Razorpay keys are not set. Add RAZORPAY_KEY_ID and RAZORPAY_KEY_SECRET to .env.' },
    },
    razorpay: { enabled: rz, key_id: rz ? 'rzp_test_PLACEHOLDER01' : null, test_mode: true },
    ...(over.owner === false ? {} : { owner: { razorpay_problem: rz ? null : 'Razorpay keys are not set.', key_secret_set: rz, webhook_secret_set: rz, webhook_url: 'http://localhost:8000/api/payments/webhooks/razorpay', upi_vpa: over.vpa ?? '', upi_payee_name: '', upi_qr_enabled: !!over.qr } }),
  }
}

export function payment(over: Partial<PaymentDetail> = {}): PaymentDetail {
  return {
    id: 7, code: 'PAY-261111-0007', order_id: 12, order_code: 'SW-261111-0012', customer_name: 'Walk-in customer', order_status: 'confirmed', method: 'cash', provider: 'none',
    status: 'pending', amount_paise: 17200, currency: 'INR', amount_received_paise: null, change_paise: 0, refunded_paise: 0, refundable_paise: 0, verified: false,
    verification: 'none', verification_label: 'Waiting for cash', reference_note: null, provider_method: null, provider_payment_id: null, failure_code: null, failure_reason: null,
    attention: null, is_synthetic: false, stale: false, created_at: '2026-11-11T13:00:00', paid_at: null, created_by: 'Test Owner', confirmed_by: null,
    provider_order_id: null, provider_qr_id: null, qr_image_url: null, upi_payee: null, refunds: [], events: [], upi: null,
    ...over,
  }
}

export function invoice(over: Partial<InvoiceData> = {}): InvoiceData {
  return {
    number: 'INV-2026-000001', issued_at: '2026-11-11T13:05:00', order_id: 12, order_code: 'SW-261111-0012', order_status: 'confirmed', ordered_at: '2026-11-11T13:00:00', is_synthetic: false,
    shop: { name: 'Patel Kirana (demo)' }, customer: { name: 'Walk-in customer', phone: null },
    items: [{ name: 'Rice', qty: 2, unit: 'kg', unit_price_paise: 5800, line_total_paise: 11600 }, { name: 'Milk', qty: 1, unit: 'l', unit_price_paise: 5600, line_total_paise: 5600 }],
    subtotal_paise: 17200, discount_paise: 0, total_paise: 17200,
    payment: { status: 'paid', method: 'cash', provider: 'none', reference: 'PAY-261111-0007', provider_payment_id: null, paid_at: '2026-11-11T13:04:00', amount_paise: 17200, refunded_paise: 0, verified: false, label: 'Cash recorded by Test Owner' },
    tax_note: 'This invoice shows the bill total as entered by the shop. It has no tax breakdown and is not a GST tax invoice.',
    ...over,
  }
}

import type { PaymentAnalytics } from '../types'
export function paymentAnalytics(over: Partial<PaymentAnalytics> = {}): PaymentAnalytics {
  const day = (period: string, cash: number, upi: number, rz: number) => ({ period, collected_paise: cash + upi + rz, count: [cash, upi, rz].filter(Boolean).length, cash_paise: cash, upi_paise: upi, razorpay_paise: rz })
  return {
    days: 30, since: '2026-10-12T00:00:00', includes_demo_orders: false,
    kpis: {
      collected_paise: 90000, refunds_paise: 5000, net_paise: 85000, paid_count: 3, average_paise: 30000, cash_paise: 50000, upi_paise: 30000, razorpay_paise: 10000, upi_manual_paise: 30000,
      pending_count: 1, pending_paise: 12000, failed_count: 2, failed_paise: 8000, refund_count: 1, refunds_waiting_count: 1, refunds_waiting_paise: 2000, needs_attention: 1,
    },
    by_method: [{ method: 'cash', collected_paise: 50000, count: 1, share: 0.5556 }, { method: 'upi', collected_paise: 30000, count: 1, share: 0.3333 }, { method: 'razorpay', collected_paise: 10000, count: 1, share: 0.1111 }],
    daily: [day('2026-11-09', 50000, 0, 0), day('2026-11-10', 0, 30000, 0), day('2026-11-11', 0, 0, 10000)],
    weekly: [day('2026-11-09', 50000, 30000, 10000)], monthly: [day('2026-11', 50000, 30000, 10000)],
    ...over,
  }
}
