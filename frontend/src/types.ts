/** The language keys the server's registry (backend/app/languages.py) defines. */
export type Lang = 'gu' | 'hi' | 'hinglish' | 'en' | 'mr' | 'bn' | 'ta' | 'te' | 'kn' | 'ml' | 'pa'
export type SttChoice = Lang | 'auto'

export type CheckStatus = 'passed' | 'failed' | 'skipped' | 'simulated' | 'not_run'
export interface CheckResult { status: CheckStatus; latency_ms?: number; audio_bytes?: number; detail?: string; voice?: string; transcript?: string; expected?: string; error_code?: string; matched?: boolean }
export interface LanguageInfo {
  key: Lang
  name: string
  native: string
  script: string
  stt_code: string
  tts_code: string
  voice: string
  default_voice: string
  voices: string[]
  enabled: boolean
  origin: 'original' | 'expansion'
  nlu_status: 'tested' | 'authored'
  tts_depth: 'deep' | 'supported'
  stt_note: string
  sample: string
  verification: { tts: CheckResult; stt_code: CheckResult; stt_loopback: CheckResult; stt_human: CheckResult }
}
export interface LanguageMode { key: 'auto' | 'mixed'; name: string; available: boolean; reason: string | null }
export interface LanguagesResponse {
  default: Lang
  stt_model: string
  tts_model: string
  modes: LanguageMode[]
  disabled: Lang[]
  docs: { stt: string; tts_voices: string; tts_text: string; checked_on: string }
  verification: { mode: 'none' | 'live' | 'simulated'; generated_at: string | null; stt_model: string | null; tts_model: string | null }
  languages: LanguageInfo[]
}

export interface CartLine {
  product_id: number
  sku: string
  name_en: string
  name_gu: string
  name_hi: string
  names?: Partial<Record<Lang, string>>   // the product's name in each other language that has one (Marathi, Bengali, ...)
  qty: string
  unit: string
  unit_price_paise: number
  line_total_paise: number
  assumed: boolean
  in_stock: number
}
export interface CartView {
  lines: CartLine[]
  total_paise: number
}
export interface PendingInfo {
  kind: string
  product: string | null
  options: { id: number; name: string }[]
  remaining: number
}
export interface ParsedLineInfo {
  spoken: string
  candidates: { id: number; sku: string; name: string }[]
  resolved: boolean
  qty: number | null
  unit: string | null
  qty_ambiguous: boolean
  match_kind: string | null
  match_score: number
  assumed_default: boolean
  unknown_term: string | null
}
export interface ParseInfo {
  intent: string
  language: Lang
  script: string
  normalized: string
  cues: Record<string, string[]>
  lines: ParsedLineInfo[]
}
export interface OrderItem {
  product_id: number
  name: string
  qty: number
  unit: string
  unit_price_paise: number
  line_total_paise: number
}
export interface Order {
  id: number
  code: string
  status: 'confirmed' | 'fulfilled' | 'cancelled'
  channel: 'voice' | 'text'
  language: string
  customer_name: string
  customer_id: number | null
  total_paise: number
  is_synthetic: boolean
  created_at: string
  session_id: string | null
  items: OrderItem[]
  /** Added in 2.7.0. status "none" means no payment was ever started: every order from before payments existed, and that is not an error. */
  payment?: OrderPaymentSummary
}
export interface StockAlert {
  product_id: number
  sku: string
  name: string
  unit: string
  stock: number
  reorder_level: number
  severity: 'low' | 'out'
}
export interface Timings {
  stt_ms: number | null
  nlu_ms: number
  tts_ms: number | null
  /** 2.6.0: the other server-side stages of a turn (validate = checking the upload, process = dialogue + stock + order, server = their sum) */
  validate_ms?: number
  db_ms?: number
  process_ms?: number
  server_ms?: number | null
}
export interface AudioInfo {
  audio_id: string | null
  audio_url: string | null
  tts_ms: number | null
  cached: boolean
  error: string | null
  voice?: string
}
export interface TurnResponse {
  session_id: string
  transcript: string
  language: Lang
  reply_text: string
  reply_lang: Lang
  phase: 'collecting' | 'confirming' | 'completed' | 'cancelled'
  awaiting: string | null
  pending: PendingInfo | null
  cart: CartView
  parse: ParseInfo
  events: { type: string; [k: string]: unknown }[]
  order: Order | null
  low_stock_alerts: StockAlert[]
  timings: Timings
  audio: AudioInfo | null
  stt?: { model: string; request_id: string; latency_ms: number; language_code: string; detected_language_code?: string | null; attempts?: number }
  no_speech?: boolean
  assistant_turn_id: number
  customer_turn_id?: number
  segment?: { id: number | null; audio_ms: number | null }
}
export interface Product {
  id: number
  sku: string
  name_en: string
  name_gu: string
  name_hi: string
  category: string
  unit: 'kg' | 'l' | 'pack' | 'pc'
  price_paise: number
  stock: number
  reorder_level: number
  pack_size: number | null
  pack_size_unit: string | null
  aliases: string[]
  default_for: string[]
  is_active: boolean
  stock_status: 'ok' | 'low' | 'out'
  brand: string
  ean: string | null
  source: 'curated' | 'manual' | 'off_india' | string
  source_ref: string | null
  price_basis: 'demo' | 'shop' | string
  cost_paise: number | null
  stock_value_paise: number
  updated_at: string
}
export interface Movement {
  id: number
  product: string
  delta: number
  reason: string
  order_id: number | null
  created_at: string
}
export interface Overview {
  window_days: number
  include_synthetic: boolean
  kpis: {
    revenue_paise: number
    orders: number
    avg_basket_paise: number
    voice_share: number
    today_revenue_paise: number
    today_orders: number
    low_stock_count: number
    out_of_stock_count: number
    cancelled: number
    non_synthetic_orders_total: number
  }
  sales_by_day: { date: string; revenue_paise: number; orders: number }[]
  top_products: { product_id: number; name: string; unit: string; revenue_paise: number; qty: number }[]
  category_mix: { category: string; revenue_paise: number }[]
  orders_by_status: { status: 'confirmed' | 'fulfilled' | 'cancelled'; orders: number }[]
  orders_by_language: { language: string; orders: number }[]
  orders_by_channel: { channel: string; orders: number }[]
  orders_by_hour: { hour: number; orders: number }[]
}
export interface ProviderLatency {
  calls: number
  ok: number
  errors: number
  p50_ms: number | null
  p95_ms: number | null
  last_error: string | null
}
export interface Latency {
  'gnani-stt': ProviderLatency
  'gnani-tts': ProviderLatency
  evon: ProviderLatency
  nlu: { turns: number; p50_ms: number | null; p95_ms: number | null }
}
export interface SessionTurn {
  id: number
  role: 'customer' | 'assistant'
  text: string
  language: string
  input_mode: string
  stt_ms: number | null
  nlu_ms: number | null
  tts_ms: number | null
  audio_id: string | null
  detail: { parse?: ParseInfo; events?: { type: string; product_id?: number; term?: string }[]; phase?: string }
  created_at: string
}
export interface SessionSummary {
  session_id: string
  phase: string
  language: string
  turns: number
  updated_at?: string
  [k: string]: unknown
}
export interface SessionSnapshot {
  session_id: string
  phase: string
  awaiting: string | null
  language: string
  customer_id?: number | null
  cart: CartView
  pending: PendingInfo | null
  turns: SessionTurn[]
  created_at: string
  updated_at: string
}
export interface PublicSettings {
  store_name: string
  gnani: {
    configured: boolean
    key_hint: string | null   // owner only
    base_url: string | null   // owner only
    stt_model: string
    stt_format: string
    stt_bias: boolean
    tts_model: string
    calls_last_hour: number
    max_calls_per_hour: number
  }
  voices: Record<Lang, string> & { speed: number; catalogue: Record<string, string[]> }
  languages: { disabled: Lang[]; env: string }
  evon: { available_on_gnani_api: boolean; configured: boolean; note: string }
  limits: { max_upload_mb: number; max_audio_seconds: number; rate_limit_per_minute: number }
  payments: PaymentConfig
}
export interface Health {
  status: string
  db: string
  products: number
  gnani_configured: boolean
  version: string
  store_name: string
  store_name_is_default: boolean
}
export interface NoiseRow {
  label: string
  kind: string | null
  snr_db: number | null
  telephony: boolean
  measured_snr_db: number | null
  transcript?: string | null
  latency_ms?: number
  wer?: number | null
  cer?: number | null
  error?: string
  parsed_lines?: { spoken: string; product: string | null; qty: number | null; unit: string | null }[]
}
export interface NoiseCondition {
  kind: 'white' | 'pink' | 'hum' | 'babble' | null
  snr_db: number | null
  telephony: boolean
}

// ------------------------------------------------------------------ v1.1: paging, customers, catalogue, analytics
export interface Paged<T> { total: number; page: number; page_size: number; items: T[] }
export interface InventoryList extends Paged<Product> { counts: { all: number; ok: number; low: number; out: number } }
export interface OrderList { total: number; limit: number; offset: number; counts: { all: number; confirmed: number; fulfilled: number; cancelled: number }; items: Order[] }

export interface Customer {
  id: number
  name: string
  phone: string
  language: '' | Lang
  notes: string
  is_synthetic: boolean
  is_active: boolean
  created_at: string
  orders: number
  spent_paise: number
  avg_basket_paise: number
  last_order_at: string | null
}
export interface CustomerDetail extends Customer {
  top_products: { product_id: number; name: string; unit: string; qty: number; revenue_paise: number }[]
  language_mix: { language: string; orders: number }[]
}

export interface CatalogItem {
  id: number
  ean: string
  name: string
  brand: string
  category: string
  pack_size: number
  pack_unit: string
  pack_label: string
  display_name: string
  last_modified: string
  source_id: string
  provenance: string
  in_shop: boolean
}
export interface CatalogDetail extends CatalogItem {
  name_raw: string
  quantity_raw: string
  off_categories_raw: string
  transforms: string[]
  split: string
  suggested_aliases: string[]
}
export interface CatalogFacets { total: number; categories: { name: string; count: number }[]; brands: { name: string; count: number }[] }
export interface CatalogSource {
  rows_loaded: number
  manifest_found: boolean
  id?: string
  title?: string
  origin?: string
  origin_url?: string
  licence?: string
  attribution?: string
  retrieved_on?: string
  snapshot_date?: string
  raw_rows?: number
  limitations?: string[]
}

export interface SalesPoint { period: string; revenue_paise: number; orders: number; avg_basket_paise: number; partial: boolean }
export interface SalesSeries {
  grain: 'day' | 'week' | 'month'
  periods: number
  include_synthetic: boolean
  series: SalesPoint[]
  totals: { revenue_paise: number; orders: number; avg_basket_paise: number }
}
export interface StockRow { product_id: number; name: string; unit: string; stock: number; reorder_level: number }
export interface InventorySummary {
  products: number
  valuation_retail_paise: number
  valuation_cost_paise: number | null
  products_with_cost: number
  price_basis: { demo: number; shop: number }
  by_category: { category: string; retail_paise: number; items: number; units_low: number }[]
  out_of_stock: StockRow[]
  low_stock: StockRow[]
  stock_health: { ok: number; low: number; out: number }
  no_sales: { days: number; items: number; retail_paise: number; top: { product_id: number; name: string; retail_paise: number }[] }
}
export interface DemandRow {
  product_id: number
  name: string
  category: string
  unit: string
  units_sold: number
  revenue_paise: number
  velocity_per_day: number
  stock: number
  days_of_cover: number | null
  trend_pct: number | null
  suggested_reorder_qty: number
  status: 'ok' | 'stockout_risk' | 'overstocked'
}
export interface DemandInsights {
  window_days: number
  include_synthetic: boolean
  method: string
  /** the earlier window used for "vs earlier": `comparable` is false when too few of its days had orders */
  previous_window: { days: number; days_with_orders: number; comparable: boolean }
  products: DemandRow[]
  stockout_risk: DemandRow[]
  rising: DemandRow[]
  falling: DemandRow[]
}

export interface SearchHit { id: number; title: string; subtitle: string }
export interface SearchResults {
  query: string
  products: SearchHit[]
  customers: SearchHit[]
  orders: SearchHit[]
  catalog: SearchHit[]
  catalog_total?: number
}
export interface CartEditResult {
  session_id: string
  phase: TurnResponse['phase']
  awaiting: string | null
  pending: PendingInfo | null
  cart: CartView
}

/* ---- accounts ---- */
export type Role = 'owner' | 'staff'
export interface AuthUser {
  id: number
  email: string
  full_name: string
  role: Role
  email_verified: boolean
  created_at: string | null
  last_login_at: string | null
  preferences: { language?: Lang }
}
export interface AuthConfig {
  signup_open: boolean
  has_owner: boolean
  owner_email_set: boolean
  email_configured: boolean
  verification_required: boolean
  password: { min_length: number; max_length: number }
  session: { hours: number; idle_minutes: number; remember_days: number }
}
export interface SessionPayload { user: AuthUser; csrf_token: string; session: { id: string; expires_at: string; remember: boolean } }
export type SoftSession = { authenticated: false } | ({ authenticated: true } & SessionPayload)
export interface SignUpResult { verification_required: boolean; user: AuthUser | null; csrf_token: string | null; email?: string }
export interface DeviceSession { id: string; device: string; created_at: string; last_seen_at: string; expires_at: string; remember: boolean; current: boolean }
export interface TeamUser extends AuthUser { is_active: boolean }
export interface ContactRow { id: number; name: string; email: string; topic: string; message: string; created_at: string; handled: boolean }

/** One product's stock over the window, from the stock ledger (GET /api/analytics/stock-movement). */
export interface StockMovementRow {
  product_id: number
  name: string
  category: string
  unit: string
  opening: number
  added: number
  returned: number
  sold: number
  written_off: number
  current: number
  reorder_level: number
  status: 'ok' | 'low' | 'out'
}
export interface StockMovementReport {
  window_days: number
  movements: number
  products_moved: number
  products_total: number
  rows: StockMovementRow[]
  truncated: boolean
  series: { date: string; in_paise: number; out_paise: number }[]
  totals: { in_paise: number; out_paise: number }
  method: string
}

/** POST /api/turns/{id}/speak: the spoken version of a reply that is already on screen. */
export interface SpeakResult {
  turn_id: number
  audio: AudioInfo
  timings: { tts_ms: number | null; server_ms?: number | null }
}
/** What the browser measured about one spoken turn (sent to POST /api/turns/{id}/client-timing). */
export interface ClientTiming {
  capture_ms?: number
  end_to_reply_ms?: number
  end_to_audio_ms?: number
  upload_bytes?: number
  endpoint?: 'manual' | 'auto' | 'live'
}

// ---- owner diagnostics (GET /api/diagnostics/voice)
export interface StatSummary { n: number; p50: number | null; p95: number | null; max: number | null; mean: number | null }
export interface GnaniCallStats extends StatSummary { calls: number; ok: number; errors: number; retried: number; error_types: { type: string; count: number }[] }
export interface SlowTurn {
  turn_id: number; at: string; mode: string | null; language: string
  server_ms: number | null; validate_ms: number | null; stt_ms: number | null; process_ms: number | null; tts_ms: number | null
  tts_cached: boolean | null; stt_attempts: number | null; end_to_reply_ms: number | null
}
export interface VoiceDiagnostics {
  window_hours: number
  generated_at: string
  voice: {
    turns: number
    by_mode: { voice: number; stream: number }
    stages: Record<'validate_ms' | 'stt_ms' | 'nlu_ms' | 'db_ms' | 'process_ms' | 'tts_ms' | 'server_ms', StatSummary>
    stage_share_of_median: Record<'validate_ms' | 'stt_ms' | 'process_ms' | 'tts_ms', number | null>
    tts_cached_share: number | null
    retried_speech_calls: number
  }
  browser_reported: {
    turns: number
    end_to_reply_ms: StatSummary; end_to_audio_ms: StatSummary; capture_ms: StatSummary
    endpoints: { kind: string; turns: number }[]
  }
  typed: { turns: number; process_ms: StatSummary }
  gnani: { stt: GnaniCallStats; tts: GnaniCallStats }
  budget: { calls_last_hour: number; max_per_hour: number }
  config: {
    stt_model: string; tts_model: string; stt_timeout_s: number; tts_timeout_s: number; connect_timeout_s: number
    tts_sample_rate: number; tts_speed: number; gnani_configured: boolean
  }
  slowest: SlowTurn[]
}

/* ------------------------------------------------------------------ payments (2.7.0) */
export type PaymentMethod = 'cash' | 'upi' | 'razorpay'
export type PaymentStatus = 'pending' | 'paid' | 'failed' | 'cancelled' | 'partially_refunded' | 'refunded'
export type OrderPaymentStatus = 'none' | PaymentStatus
export interface OrderPaymentSummary {
  status: OrderPaymentStatus
  paid_paise: number
  refunded_paise: number
  method: PaymentMethod | null
  payment_id: number | null
  pending_payment_id: number | null
}
export interface PaymentConfig {
  mode: 'test' | 'live'
  currency: 'INR'
  gst_configured: boolean
  pending_minutes: number
  methods: {
    cash: { available: boolean; reason: string | null }
    upi: { available: boolean; mode: 'provider' | 'manual' | null; reason: string | null }
    razorpay: { available: boolean; reason: string | null }
  }
  razorpay: { enabled: boolean; key_id: string | null; test_mode: boolean }
  /** Owner only. Says whether the secrets are set, never what they are. */
  owner?: { razorpay_problem: string | null; key_secret_set: boolean; webhook_secret_set: boolean; webhook_url: string; upi_vpa: string; upi_payee_name: string; upi_qr_enabled: boolean }
}
export interface UpiInstructions {
  mode: 'provider' | 'manual'
  verified_by_provider: boolean
  uri: string | null
  qr_image_url: string | null
  payee: string | null
  amount_paise: number
  reference: string
  order_code: string
  instructions: string
}
export interface PaymentRefund {
  id: number
  code: string
  payment_id: number
  kind: 'provider' | 'manual'
  amount_paise: number
  status: 'pending' | 'processed' | 'failed'
  reason: string
  provider_refund_id: string | null
  speed_processed: string | null
  failure_reason: string | null
  label: string
  initiated_by: string | null
  created_at: string | null
  processed_at: string | null
}
export interface PaymentEventRow {
  id: number
  source: 'webhook' | 'checkout' | 'user' | 'system'
  type: string
  message: string
  status_before: string | null
  status_after: string | null
  signature_ok: boolean | null
  actor: string | null
  created_at: string | null
}
export interface Payment {
  id: number
  code: string
  order_id: number
  order_code: string
  customer_name: string
  order_status: Order['status']
  method: PaymentMethod
  provider: 'none' | 'manual' | 'razorpay' | 'razorpay_qr'
  status: PaymentStatus
  amount_paise: number
  currency: string
  amount_received_paise: number | null
  change_paise: number
  refunded_paise: number
  refundable_paise: number
  verified: boolean
  verification: 'none' | 'cash' | 'manual' | 'signature' | 'webhook' | 'provider'
  verification_label: string
  reference_note: string | null
  provider_method: string | null
  provider_payment_id: string | null
  failure_code: string | null
  failure_reason: string | null
  attention: string | null
  is_synthetic: boolean
  stale: boolean
  created_at: string | null
  paid_at: string | null
  created_by: string | null
  confirmed_by: string | null
}
export interface PaymentCheckout { key_id: string; provider_order_id: string; amount_paise: number; currency: string; name: string; description: string; mode: 'test' | 'live' }
export interface PaymentDetail extends Payment {
  provider_order_id: string | null
  provider_qr_id: string | null
  qr_image_url: string | null
  upi_payee: string | null
  refunds: PaymentRefund[]
  events: PaymentEventRow[]
  upi: UpiInstructions | null
  /** Only while a Razorpay payment is waiting. Holds the public key id, never a secret. */
  checkout?: PaymentCheckout
  /** A plain sentence when the answer could not be completed (for example Razorpay could not be reached). */
  notice?: string
}
export interface PaymentList {
  total: number
  limit: number
  offset: number
  counts: Record<PaymentStatus | 'all', number>
  items: Payment[]
}
export interface OrderPayments { order_id: number; order_code: string; total_paise: number; summary: OrderPaymentSummary; items: Payment[] }
export interface PaymentAnalytics {
  days: number
  since: string
  includes_demo_orders: boolean
  kpis: {
    collected_paise: number; refunds_paise: number; net_paise: number; paid_count: number; average_paise: number
    cash_paise: number; upi_paise: number; razorpay_paise: number; upi_manual_paise: number
    pending_count: number; pending_paise: number; failed_count: number; failed_paise: number; refund_count: number
    refunds_waiting_count: number; refunds_waiting_paise: number; needs_attention: number
  }
  by_method: { method: PaymentMethod; collected_paise: number; count: number; share: number }[]
  daily: PaymentTrendPoint[]
  weekly: PaymentTrendPoint[]
  monthly: PaymentTrendPoint[]
}
export interface PaymentTrendPoint { period: string; collected_paise: number; count: number; cash_paise: number; upi_paise: number; razorpay_paise: number }
export interface InvoiceData {
  number: string
  issued_at: string | null
  order_id: number
  order_code: string
  order_status: Order['status']
  ordered_at: string | null
  is_synthetic: boolean
  shop: { name: string }
  customer: { name: string; phone: string | null }
  items: { name: string; qty: number; unit: string; unit_price_paise: number; line_total_paise: number }[]
  subtotal_paise: number
  discount_paise: number
  total_paise: number
  payment: null | {
    status: PaymentStatus; method: PaymentMethod; provider: string; reference: string; provider_payment_id: string | null
    paid_at: string | null; amount_paise: number; refunded_paise: number; verified: boolean; label: string
  }
  tax_note: string
}
