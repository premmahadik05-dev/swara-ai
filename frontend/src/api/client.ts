import type { EvaluationResponse } from '../lib/evaluation'
import type {
  CartEditResult, CatalogDetail, CatalogFacets, CatalogItem, CatalogSource, Customer, CustomerDetail, DemandInsights, Health,
  InventoryList, InventorySummary, Latency, LanguagesResponse, Movement, NoiseCondition, NoiseRow, Order, OrderList, Overview, Paged, Product,
  PublicSettings, SalesSeries, SearchResults, SessionSnapshot, SessionSummary, StockAlert, StockMovementReport, TurnResponse,
  AuthConfig, AuthUser, ContactRow, DeviceSession, SessionPayload, SignUpResult, SoftSession, TeamUser,
  ClientTiming, SpeakResult, VoiceDiagnostics,
  InvoiceData, OrderPayments, PaymentAnalytics, PaymentConfig, PaymentDetail, PaymentList, PaymentMethod, PaymentRefund,
} from '../types'

export class ApiError extends Error {
  status: number
  code: string
  constructor(status: number, code: string, message: string) {
    super(message)
    this.status = status
    this.code = code
  }
}

// The session itself is an HttpOnly cookie the browser handles; JavaScript never sees it. What JavaScript holds, in memory only,
// is the per-session CSRF token that the server asks for on every write.
let csrf = ''
export const csrfToken = { get: () => csrf, set: (v: string | null) => { csrf = v ?? '' } }

// Called when a protected request is refused because the session ended (so the app can send the person back to sign in).
let onUnauthorized: ((code: string) => void) | null = null
export const setUnauthorizedHandler = (fn: ((code: string) => void) | null) => { onUnauthorized = fn }

/** Turn any FastAPI error body into an ApiError with a message a shopkeeper can act on. */
export async function toApiError(res: Response): Promise<ApiError> {
  let code = `HTTP_${res.status}`
  let message = res.statusText || 'Request failed'
  try {
    const body = await res.json()
    const d = body?.detail
    if (typeof d === 'string') message = d
    else if (Array.isArray(d)) message = d.map((x: { msg?: string }) => x.msg).filter(Boolean).slice(0, 2).join('; ') || message
    else if (d && typeof d === 'object') {
      code = d.code ?? code
      message = d.message ?? message
    }
  } catch { /* non-JSON body */ }
  if (res.status === 401 && code.startsWith('HTTP_')) message = 'Sign in to continue.'
  if (res.status === 403 && code.startsWith('HTTP_')) message = 'You do not have permission to do this.'
  if (res.status === 429 && code.startsWith('HTTP_')) message = 'Too many requests. Wait a moment and try again.'
  return new ApiError(res.status, code, message)
}

// Identical GETs that are already in flight share one network call; a few slow-changing lookups are also kept for a short time.
// Every write clears the cache, so a screen that reloads after saving never sees stale data.
const inflight = new Map<string, Promise<unknown>>()
const cache = new Map<string, { at: number; value: unknown }>()
export const clearApiCache = () => { cache.clear(); inflight.clear() }

async function send<T>(path: string, init: RequestInit): Promise<T> {
  const headers = new Headers(init.headers)
  if (csrf && (init.method ?? 'GET').toUpperCase() !== 'GET') headers.set('X-CSRF-Token', csrf)
  if (init.body && typeof init.body === 'string' && !headers.has('Content-Type')) headers.set('Content-Type', 'application/json')
  let res: Response
  try {
    res = await fetch(path, { ...init, headers })
  } catch {
    throw new ApiError(0, 'NETWORK', 'Cannot reach the SWARA AI server. Is the backend running?')
  }
  if (!res.ok) {
    const err = await toApiError(res)
    // A 401 on anything except the sign-in/sign-up forms themselves means the session is gone.
    if (res.status === 401 && !path.startsWith('/api/auth/')) onUnauthorized?.(err.code)
    throw err
  }
  return (await res.json()) as T
}

async function request<T>(path: string, init: RequestInit = {}, ttlMs = 0): Promise<T> {
  const method = (init.method ?? 'GET').toUpperCase()
  if (method !== 'GET') {
    try { return await send<T>(path, init) } finally { clearApiCache() }
  }
  const hit = cache.get(path)
  if (ttlMs && hit && Date.now() - hit.at < ttlMs) return hit.value as T
  const running = inflight.get(path)
  if (running) return running as Promise<T>
  const p = send<T>(path, init)
    .then((v) => { if (ttlMs) cache.set(path, { at: Date.now(), value: v }); return v })
    .finally(() => { inflight.delete(path) })
  inflight.set(path, p)
  return p
}

export interface CsvFile { blob: Blob; filename: string; truncated: boolean }

/** Fetch a CSV export. Done with fetch (not a plain link) so an ended session or a refused request shows a message instead of saving an error page as a file. */
async function download(path: string): Promise<CsvFile> {
  let res: Response
  try {
    res = await fetch(path)
  } catch {
    throw new ApiError(0, 'NETWORK', 'Cannot reach the SWARA AI server. Is the backend running?')
  }
  if (!res.ok) {
    const err = await toApiError(res)
    if (res.status === 401) onUnauthorized?.(err.code)
    throw err
  }
  const filename = /filename="([^"]+)"/.exec(res.headers.get('Content-Disposition') ?? '')?.[1] ?? 'swara-export.csv'
  return { blob: await res.blob(), filename, truncated: res.headers.get('X-Export-Truncated') === 'true' }
}

const qs = (o: Record<string, string | number | boolean | undefined | null>) => {
  const p = new URLSearchParams()
  Object.entries(o).forEach(([k, v]) => v !== undefined && v !== null && v !== '' && p.set(k, String(v)))
  const s = p.toString()
  return s ? `?${s}` : ''
}
const json = (method: string, body: unknown): RequestInit => ({ method, body: JSON.stringify(body) })

export const api = {
  // ---- accounts
  authConfig: () => request<AuthConfig>('/api/auth/config', {}, 30000),
  authSession: () => request<SoftSession>('/api/auth/session'),
  signUp: (b: { full_name: string; email: string; password: string; confirm_password: string; accept_terms: boolean }) =>
    request<SignUpResult>('/api/auth/signup', json('POST', b)),
  signIn: (b: { email: string; password: string; remember: boolean }) => request<Pick<SessionPayload, 'user' | 'csrf_token'>>('/api/auth/login', json('POST', b)),
  signOut: () => request<{ ok: boolean }>('/api/auth/logout', { method: 'POST' }),
  forgotPassword: (email: string) => request<{ email_configured: boolean; message: string }>('/api/auth/forgot', json('POST', { email })),
  resetPassword: (token: string, password: string, confirm_password: string) => request<{ ok: boolean }>('/api/auth/reset', json('POST', { token, password, confirm_password })),
  verifyEmail: (token: string) => request<{ ok: boolean }>('/api/auth/verify-email', json('POST', { token })),
  resendVerification: (email: string) => request<{ ok: boolean; message: string }>('/api/auth/resend-verification', json('POST', { email })),
  updateProfile: (b: { full_name?: string; language?: string }) => request<{ user: AuthUser }>('/api/auth/profile', json('PATCH', b)),
  changePassword: (current_password: string, new_password: string) =>
    request<{ ok: boolean; other_sessions_signed_out: number }>('/api/auth/change-password', json('POST', { current_password, new_password })),
  deviceSessions: () => request<DeviceSession[]>('/api/auth/sessions'),
  revokeDeviceSession: (id: string) => request<{ ok: boolean; current: boolean }>(`/api/auth/sessions/${id}`, { method: 'DELETE' }),
  revokeOtherSessions: () => request<{ signed_out: number }>('/api/auth/sessions/revoke-others', { method: 'POST' }),
  team: () => request<TeamUser[]>('/api/auth/users'),
  setUserActive: (id: number, active: boolean) => request<TeamUser>(`/api/auth/users/${id}/active`, json('POST', { active })),
  contact: (b: { name: string; email: string; topic: string; message: string; website?: string }) =>
    request<{ ok: boolean; forwarded: boolean; message: string }>('/api/contact', json('POST', b)),
  contactMessages: () => request<ContactRow[]>('/api/contact/messages'),
  markMessageHandled: (id: number) => request<{ ok: boolean }>(`/api/contact/messages/${id}/handled`, { method: 'POST' }),

  // ---- shop
  health: () => request<Health>('/api/health', {}, 8000),
  parse: (text: string, language?: string | null) => request<TurnResponse>('/api/text/parse', json('POST', { text, language: language || undefined })),
  /** ``language`` is the one chosen in the selector; it is a hint for reading the text (pass nothing, or 'auto', to detect it from the text). */
  textTurn: (text: string, sessionId?: string | null, speak = false, customerId?: number | null, language?: string | null) =>
    request<TurnResponse>('/api/text/turn', json('POST', { text, session_id: sessionId || undefined, speak, customer_id: customerId || undefined, language: language || undefined })),
  /** The server's language registry: what is on offer, which voice, and what has been verified live. */
  languages: () => request<LanguagesResponse>('/api/languages', {}, 30000),
  voiceTurn: (wav: Blob, o: { language: string; sessionId?: string | null; speak: boolean; customerId?: number | null }) => {
    const f = new FormData()
    f.append('audio', wav, 'order.wav')
    f.append('language', o.language)
    f.append('speak_reply', String(o.speak))
    if (o.sessionId) f.append('session_id', o.sessionId)
    if (o.customerId) f.append('customer_id', String(o.customerId))
    return request<TurnResponse>('/api/voice/turn', { method: 'POST', body: f })
  },
  /** The spoken version of a reply already on screen (the app asks for it after showing the reply, so the screen never waits for the voice). */
  speakTurn: (turnId: number) => request<SpeakResult>(`/api/turns/${turnId}/speak`, { method: 'POST' }),
  /** Best effort: what the browser measured for a spoken turn. */
  clientTiming: (turnId: number, t: ClientTiming) => request<{ ok: boolean }>(`/api/turns/${turnId}/client-timing`, json('POST', t)),
  /** Owner only. */
  voiceDiagnostics: (hours = 168) => request<VoiceDiagnostics>(`/api/diagnostics/voice${qs({ hours })}`),
  confirm: (sessionId: string, customerId?: number | null) =>
    request<TurnResponse>(`/api/sessions/${sessionId}/confirm`, customerId ? json('POST', { customer_id: customerId }) : { method: 'POST' }),
  editCart: (sessionId: string, productId: number, qty: number, mode: 'set' | 'add' = 'set') =>
    request<CartEditResult>(`/api/sessions/${sessionId}/cart`, json('POST', { product_id: productId, qty: String(qty), mode })),
  newSession: () => request<{ session_id: string }>('/api/sessions', { method: 'POST' }),
  sessions: (limit = 20) => request<SessionSummary[]>(`/api/sessions${qs({ limit })}`),
  session: (id: string) => request<SessionSnapshot>(`/api/sessions/${id}`),

  products: (p: { q?: string; category?: string; status?: string } = {}) => request<Product[]>(`/api/products${qs(p)}`),
  inventory: (p: { q?: string; category?: string; status?: string; source?: string; sort?: string; page?: number; page_size?: number } = {}) =>
    request<InventoryList>(`/api/inventory${qs(p)}`),
  exportInventory: (p: { q?: string; category?: string; status?: string; source?: string; sort?: string } = {}) =>
    download(`/api/inventory/export.csv${qs(p)}`),
  product: (id: number) => request<Product>(`/api/products/${id}`),
  createProduct: (body: Partial<Product> & { sku: string; name_en: string; unit: string; price_paise: number }) =>
    request<Product>('/api/products', json('POST', body)),
  patchProduct: (id: number, body: Partial<Product>) => request<Product>(`/api/products/${id}`, json('PATCH', body)),
  restock: (id: number, qty: number) => request<Product>(`/api/products/${id}/restock`, json('POST', { qty: String(qty) })),
  alerts: () => request<StockAlert[]>('/api/inventory/alerts'),
  categories: () => request<{ category: string; count: number }[]>('/api/inventory/categories', {}, 20000),
  movements: (limit = 15) => request<Movement[]>(`/api/inventory/movements${qs({ limit })}`),

  orders: (p: { status?: string; channel?: string; language?: string; q?: string; customer_id?: number; sort?: string; include_synthetic?: boolean; limit?: number; offset?: number }) =>
    request<OrderList>(`/api/orders${qs(p)}`),
  exportOrders: (p: { status?: string; channel?: string; language?: string; q?: string; customer_id?: number; sort?: string; include_synthetic?: boolean }) =>
    download(`/api/orders/export.csv${qs(p)}`),
  order: (id: number) => request<Order>(`/api/orders/${id}`),
  setOrderStatus: (id: number, status: 'fulfilled' | 'cancelled') => request<Order>(`/api/orders/${id}/status`, json('POST', { status })),

  // ---- payments (2.7.0). The amount is never sent: the server charges the order's own total.
  paymentConfig: () => request<PaymentConfig>('/api/payments/config', {}, 15000),
  payments: (p: { status?: string; method?: string; q?: string; since?: string; until?: string; include_synthetic?: boolean; attention?: boolean; sort?: string; limit?: number; offset?: number }) =>
    request<PaymentList>(`/api/payments${qs(p)}`),
  payment: (id: number) => request<PaymentDetail>(`/api/payments/${id}`),
  orderPayments: (orderId: number) => request<OrderPayments>(`/api/orders/${orderId}/payments`),
  startPayment: (orderId: number, method: PaymentMethod, idempotencyKey: string) =>
    request<PaymentDetail>(`/api/orders/${orderId}/payments`, json('POST', { method, idempotency_key: idempotencyKey })),
  recordCash: (id: number, receivedPaise: number) => request<PaymentDetail>(`/api/payments/${id}/cash`, json('POST', { received_paise: receivedPaise })),
  confirmUpi: (id: number, reference: string) => request<PaymentDetail>(`/api/payments/${id}/confirm-upi`, json('POST', { reference })),
  verifyRazorpay: (id: number, r: { razorpay_order_id: string; razorpay_payment_id: string; razorpay_signature: string }) =>
    request<PaymentDetail>(`/api/payments/${id}/razorpay/verify`, json('POST', r)),
  refreshPayment: (id: number) => request<PaymentDetail>(`/api/payments/${id}/refresh`, { method: 'POST' }),
  cancelPayment: (id: number, reason = '') => request<PaymentDetail>(`/api/payments/${id}/cancel`, json('POST', { reason })),
  /** Owner only. ``amountPaise`` left out refunds whatever is left. */
  refund: (id: number, b: { amountPaise?: number; reason: string; idempotencyKey: string }) =>
    request<PaymentRefund & { payment: unknown }>(`/api/payments/${id}/refunds`, json('POST', { amount_paise: b.amountPaise, reason: b.reason, idempotency_key: b.idempotencyKey })),
  refreshRefund: (id: number) => request<PaymentRefund & { notice: string | null }>(`/api/refunds/${id}/refresh`, { method: 'POST' }),
  invoice: (orderId: number) => request<InvoiceData>(`/api/orders/${orderId}/invoice`),
  paymentAnalytics: (days: number, includeSynthetic: boolean) => request<PaymentAnalytics>(`/api/payments/analytics${qs({ days, include_synthetic: includeSynthetic })}`),

  customers: (p: { q?: string; sort?: string; include_synthetic?: boolean; page?: number; page_size?: number } = {}) =>
    request<Paged<Customer>>(`/api/customers${qs(p)}`),
  exportCustomers: (p: { q?: string; sort?: string; include_synthetic?: boolean } = {}) => download(`/api/customers/export.csv${qs(p)}`),
  customer: (id: number) => request<CustomerDetail>(`/api/customers/${id}`),
  createCustomer: (body: { name: string; phone?: string; language?: string; notes?: string }) => request<Customer>('/api/customers', json('POST', body)),
  patchCustomer: (id: number, body: Partial<{ name: string; phone: string; language: string; notes: string }>) =>
    request<CustomerDetail>(`/api/customers/${id}`, json('PATCH', body)),

  catalog: (p: { q?: string; category?: string; brand?: string; unit?: string; sort?: string; page?: number; page_size?: number } = {}) =>
    request<Paged<CatalogItem>>(`/api/catalog${qs(p)}`),
  catalogItem: (id: number) => request<CatalogDetail>(`/api/catalog/${id}`),
  catalogFacets: () => request<CatalogFacets>('/api/catalog/facets', {}, 60000),
  catalogSource: () => request<CatalogSource>('/api/catalog/source', {}, 60000),
  importCatalogItem: (id: number, body: { price_paise: number; stock?: number; reorder_level?: number; cost_paise?: number | null }) =>
    request<Product>(`/api/catalog/${id}/import`, json('POST', { stock: 0, reorder_level: 0, ...body })),

  search: (q: string, limit = 5) => request<SearchResults>(`/api/search${qs({ q, limit })}`),

  salesSeries: (grain: 'day' | 'week' | 'month', periods: number, includeSynthetic: boolean) =>
    request<SalesSeries>(`/api/analytics/sales${qs({ grain, periods, include_synthetic: includeSynthetic })}`),
  inventorySummary: () => request<InventorySummary>('/api/analytics/inventory'),
  demand: (days: number, includeSynthetic: boolean) => request<DemandInsights>(`/api/analytics/demand${qs({ days, include_synthetic: includeSynthetic })}`),

  overview: (days: number, includeSynthetic: boolean) => request<Overview>(`/api/analytics/overview${qs({ days, include_synthetic: includeSynthetic })}`),
  latency: () => request<Latency>('/api/analytics/latency'),
  stockMovement: (days: number) => request<StockMovementReport>(`/api/analytics/stock-movement${qs({ days })}`),
  evaluation: () => request<EvaluationResponse>('/api/evaluation'),

  settings: () => request<PublicSettings>('/api/settings', {}, 15000),
  putSettings: (body: Record<string, unknown>) => request<PublicSettings>('/api/settings', json('PUT', body)),
  putKey: (api_key: string) => request<PublicSettings>('/api/settings/gnani-key', json('PUT', { api_key })),
  testGnani: (language = 'en') =>
    request<{
      language: string
      loopback: boolean
      phrase: string
      tts: { ok: boolean; latency_ms?: number; bytes?: number; error?: string; code?: string; voice?: string }
      stt: { ok: boolean; latency_ms?: number; transcript?: string; model?: string; error?: string; code?: string }
    }>(`/api/settings/test-gnani?language=${encodeURIComponent(language)}`, { method: 'POST' }),

  noisePreview: async (wav: Blob, c: NoiseCondition): Promise<{ url: string; measured: string | null }> => {
    const f = new FormData()
    f.append('audio', wav, 'clip.wav')
    if (c.kind) { f.append('kind', c.kind); f.append('snr_db', String(c.snr_db ?? 10)) }
    f.append('telephony', String(c.telephony))
    const headers = new Headers()
    if (csrf) headers.set('X-CSRF-Token', csrf)
    const res = await fetch('/api/noise/preview', { method: 'POST', body: f, headers })
    if (!res.ok) {
      const err = await toApiError(res)
      if (res.status === 401) onUnauthorized?.(err.code)
      throw err
    }
    return { url: URL.createObjectURL(await res.blob()), measured: res.headers.get('X-Measured-SNR-dB') }
  },
  noiseRun: (wav: Blob, conditions: NoiseCondition[], language: string, reference: string) => {
    const f = new FormData()
    f.append('audio', wav, 'clip.wav')
    f.append('conditions', JSON.stringify(conditions))
    f.append('language', language)
    f.append('reference_text', reference)
    return request<{ results: NoiseRow[] }>('/api/noise/run', { method: 'POST', body: f })
  },
}

/** WebSocket URL of the realtime proxy (same origin; Vite proxies it in dev). */
export function wsUrl(language: string, sessionId?: string | null, speak = true, customerId?: number | null): string {
  const proto = location.protocol === 'https:' ? 'wss' : 'ws'
  // defer_audio: the reply and the bill arrive first, the spoken reply follows as its own message
  const q = new URLSearchParams({ language, speak_reply: String(speak), defer_audio: 'true' })
  if (sessionId) q.set('session_id', sessionId)
  if (customerId) q.set('customer_id', String(customerId))
  return `${proto}://${location.host}/ws/voice?${q}`
}
