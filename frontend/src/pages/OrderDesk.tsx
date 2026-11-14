import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import { ApiError, api, clearApiCache, wsUrl } from '../api/client'
import { useAuth } from '../lib/auth'
import { Bill } from '../components/desk/Bill'
import { Icon } from '../components/Icons'
import { LanguageSelector } from '../components/LanguageSelector'
import { PayStatusBadge } from '../components/payments/badges'
import { PaymentDialog } from '../components/payments/PaymentDialog'
import { QuickReplies } from '../components/QuickReplies'
import { useToast } from '../components/Toast'
import { Badge, Button, ErrorNote, Note, PageHeader, Seg } from '../components/ui'
import { MicCapture, MicError, WavRecorder, floatToPcm16 } from '../lib/audio'
import { clearOpenSession, loadOpenSession, saveOpenSession } from '../lib/openSession'
import { LANG_LATIN, ms, rupees } from '../lib/format'
import { useAsync } from '../lib/hooks'
import { htmlLang, htmlLangOf } from '../lib/languages'
import { firstEnabled, useLanguages } from '../lib/useLanguages'
import type { AudioInfo, CartView, Customer, Lang, Order, OrderPaymentSummary, PendingInfo, Product, StockAlert, SttChoice, TurnResponse } from '../types'

interface Msg { id: number; who: 'you' | 'bot'; text: string; lang?: string; chips: string[] }
const EMPTY_CART: CartView = { lines: [], total_paise: 0 }
const MAX_RECORD_S = 28
const SAMPLES = ['2 kilo chawal aur 1 litre doodh', 'બે કિલો ખાંડ અને એક કિલો લોટ', 'एक किलो दाल चाहिए', 'sabudana hai kya']
/** Errors that mean "this language choice is not available on this server": the list is refreshed so the selector shows what is on offer now. */
const LANGUAGE_ERRORS = new Set(['LANGUAGE_DISABLED', 'AUTO_DETECT_NEEDS_V3', 'BAD_LANGUAGE'])
type Orb = 'idle' | 'connecting' | 'listening' | 'hearing' | 'thinking' | 'preparing' | 'speaking'
const STEPS = ['Listening', 'Transcribing', 'Understanding', 'Replying'] as const
/** Where a spoken turn's clock started: the moment the recording stopped (or the live service said it was processing). */
interface Mark { endAt: number; capture: number; endpoint: 'manual' | 'auto' | 'live' }
interface Retry { wav: Blob; mark: Mark }
/** A failure that may well go away on its own (no network, a slow service, a busy one): worth offering "Try again" for the recording that was kept. */
function transient(e: unknown): boolean {
  if (!(e instanceof ApiError)) return false
  return e.status === 0 || e.status === 429 || e.status >= 500 || e.code === 'TIMEOUT' || e.code === 'NETWORK'
}
const AUTO_KEY = 'swara.autoSend'
const readAuto = () => { try { return localStorage.getItem(AUTO_KEY) !== '0' } catch { return true } }

export default function OrderDesk() {
  const { toast } = useToast()
  const health = useAsync(() => api.health(), [])
  const keySet = health.data?.gnani_configured ?? false

  const langs = useLanguages()
  const { user } = useAuth()
  const [stt, setStt] = useState<SttChoice>(user?.preferences.language ?? 'gu')
  const [mode, setMode] = useState<'tap' | 'live'>('tap')
  const [speak, setSpeak] = useState(true)
  const [session, setSession] = useState<string | null>(null)
  const [msgs, setMsgs] = useState<Msg[]>([])
  const [cart, setCart] = useState<CartView>(EMPTY_CART)
  const [pending, setPending] = useState<PendingInfo | null>(null)
  const [awaiting, setAwaiting] = useState<string | null>(null)
  const [phase, setPhase] = useState<string>('collecting')
  const [detected, setDetected] = useState<Lang>('en')
  const [order, setOrder] = useState<Order | null>(null)
  const [paying, setPaying] = useState(false)
  const [paySummary, setPaySummary] = useState<OrderPaymentSummary | null>(null)
  const [alerts, setAlerts] = useState<StockAlert[]>([])
  const [customer, setCustomer] = useState<Customer | null>(null)
  const [busy, setBusy] = useState(false)
  const [busyLines, setBusyLines] = useState<Set<number>>(new Set())
  const [recording, setRecording] = useState(false)
  const [level, setLevel] = useState(0)
  const [liveState, setLiveState] = useState<'off' | 'connecting' | 'listening' | 'hearing' | 'processing'>('off')
  const [speaking, setSpeaking] = useState(false)
  const [preparing, setPreparing] = useState(false)   // the reply is on screen and its voice is being made
  const [autoSend, setAutoSend] = useState(readAuto)
  const [retry, setRetry] = useState<Retry | null>(null)
  const [restored, setRestored] = useState(false)
  const [err, setErr] = useState<Error | null>(null)
  const [text, setText] = useState('')
  const sessionRef = useRef<string | null>(null)
  const customerRef = useRef<number | null>(null)
  const idRef = useRef(1)
  const recRef = useRef<WavRecorder | null>(null)
  const autoStop = useRef<ReturnType<typeof setTimeout> | null>(null)
  const wsRef = useRef<WebSocket | null>(null)
  const micRef = useRef<MicCapture | null>(null)
  const playing = useRef(false)
  const stopTapRef = useRef<(how?: 'manual' | 'auto') => Promise<void>>(async () => undefined)
  const markRef = useRef<Map<number, Mark & { replyMs?: number }>>(new Map())   // live mode: per reply, when its clock started
  const processingAt = useRef(0)
  const talkRef = useRef<HTMLDivElement>(null)
  sessionRef.current = session
  customerRef.current = customer?.id ?? null

  const displayLang: Lang = stt === 'auto' ? detected : stt
  const autoOk = langs.modes.find((m) => m.key === 'auto')?.available ?? false
  // A saved choice can stop being available (a language was switched off, or the model changed): fall back to one that is, rather than failing on the next turn.
  useEffect(() => {
    if (langs.loading || !langs.data) return
    if (stt === 'auto' ? !autoOk : !langs.enabledKeys.includes(stt)) setStt(firstEnabled(langs.options))
  }, [autoOk, langs.data, langs.enabledKeys, langs.loading, langs.options, stt])
  const sampleSentences = useMemo(() => {
    const mine = stt === 'auto' ? undefined : langs.options.find((o) => o.key === stt)?.info?.sample
    return [...(mine ? [mine] : []), ...SAMPLES.filter((x) => x !== mine)].slice(0, 4)
  }, [langs.options, stt])

  useEffect(() => { talkRef.current?.scrollTo({ top: talkRef.current.scrollHeight }) }, [msgs])
  useEffect(() => () => { void micRef.current?.stop(); wsRef.current?.close(); void recRef.current?.stop().catch(() => undefined) }, [])

  // An open bill from this tab (after a reload, or coming back from another page) is picked up where it was left.
  useEffect(() => {
    const id = loadOpenSession()
    if (!id) return
    let live = true
    api.session(id).then(async (snap) => {
      if (!live) return
      if (snap.phase === 'completed' || snap.phase === 'cancelled' || (!snap.cart.lines.length && snap.turns.length === 0)) { clearOpenSession(); return }
      setSession(snap.session_id); sessionRef.current = snap.session_id
      setCart(snap.cart); setPending(snap.pending); setAwaiting(snap.awaiting); setPhase(snap.phase); setDetected(snap.language as Lang)
      setMsgs(snap.turns.map((t) => ({ id: idRef.current++, who: t.role === 'customer' ? 'you' as const : 'bot' as const, text: t.text, lang: t.language, chips: [] })))
      setRestored(true)
      if (snap.customer_id) { try { const c = await api.customer(snap.customer_id); if (live) setCustomer(c) } catch { /* the bill is restored without the customer chip */ } }
    }).catch(() => clearOpenSession())
    return () => { live = false }
  }, [])

  const play = useCallback((url: string | null | undefined, onStarted?: () => void) => {
    if (!url) return
    const a = new Audio(url)
    playing.current = true
    setSpeaking(true)
    const done = () => { playing.current = false; setSpeaking(false) }
    a.onended = a.onerror = done
    a.play().then(() => onStarted?.()).catch(() => { done(); toast('Your browser blocked auto-play. Tap the page once and try again.', 'info') })
  }, [toast])

  const apply = useCallback((r: TurnResponse, via: string): number => {
    setSession(r.session_id)
    sessionRef.current = r.session_id
    if (r.no_speech || !r.cart) {
      // Nothing was heard: say so and leave the bill exactly as it was (the reply carries no new bill).
      const id = idRef.current++
      setMsgs((m) => [...m, { id, who: 'bot' as const, text: r.reply_text, lang: r.reply_lang, chips: ['no speech heard'] }])
      saveOpenSession(r.session_id)
      return id
    }
    setCart(r.cart); setPending(r.pending); setAwaiting(r.awaiting); setPhase(r.phase); setDetected(r.language)
    if (r.order) { setOrder(r.order); setAlerts(r.low_stock_alerts) }
    const chipsYou = [LANG_LATIN[r.language] ?? r.language, via === 'voice' ? 'spoken' : via === 'live' ? 'live' : 'typed']
    if (r.timings.stt_ms) chipsYou.push(`speech ${ms(r.timings.stt_ms)}`)
    const chipsBot = [`understood in ${ms(r.timings.nlu_ms)}`]
    if (r.audio?.tts_ms) chipsBot.push(`voice ${ms(r.audio.tts_ms)}`)
    else if (r.audio?.cached) chipsBot.push('voice cached')
    const youId = r.transcript ? idRef.current++ : 0   // ids are taken here, not inside the updater, which React may run twice
    const botId = idRef.current++
    setMsgs((m) => [
      ...m,
      ...(r.transcript ? [{ id: youId, who: 'you' as const, text: r.transcript, lang: r.language, chips: chipsYou }] : []),
      { id: botId, who: 'bot' as const, text: r.reply_text, lang: r.reply_lang, chips: chipsBot },
    ])
    if (r.audio?.error && speak) toast(r.audio.error, 'info')
    if (speak && r.audio?.audio_url) play(r.audio.audio_url)
    if (r.order) { toast(`Order ${r.order.code} saved. Stock updated.`, 'ok'); clearOpenSession() } else saveOpenSession(r.session_id)
    return botId
  }, [speak, play, toast])

  /** Adds "voice 480 ms" (or "voice cached") to a reply once its voice is ready. */
  const addVoiceChip = useCallback((botId: number, a: { tts_ms: number | null; cached: boolean }) => {
    const chip = a.tts_ms ? `voice ${ms(a.tts_ms)}` : a.cached ? 'voice cached' : null
    if (chip) setMsgs((m) => m.map((x) => (x.id === botId ? { ...x, chips: [...x.chips, chip] } : x)))
  }, [])

  /**
   * The reply and the bill are already on screen. Fetch the spoken reply now (a second, separate request), play it as soon as it is ready,
   * and tell the server how long the person waited. Nothing here can hold up the screen, and a voice that fails leaves the written reply.
   */
  const deliverVoice = useCallback(async (r: TurnResponse, botId: number, mark?: Mark & { replyMs?: number; bytes?: number }) => {
    const id = r.assistant_turn_id
    const report = (extra: { end_to_audio_ms?: number }) => {
      if (!mark || !id) return
      void api.clientTiming(id, { capture_ms: Math.round(mark.capture), end_to_reply_ms: mark.replyMs, upload_bytes: mark.bytes, endpoint: mark.endpoint, ...extra }).catch(() => undefined)
    }
    if (!speak || !keySet || !id) { report({}); return }
    setPreparing(true)
    try {
      const sp = await api.speakTurn(id)
      addVoiceChip(botId, { tts_ms: sp.audio.tts_ms, cached: sp.audio.cached })
      if (sp.audio.error) { toast(sp.audio.error, 'info'); report({}); return }
      play(sp.audio.audio_url, () => report({ end_to_audio_ms: mark ? Math.round(performance.now() - mark.endAt) : undefined }))
    } catch (e) {
      toast(e instanceof Error ? `The reply is on screen, but its voice could not be made: ${e.message}` : 'The reply is on screen, but its voice could not be made.', 'info')
      report({})
    } finally { setPreparing(false) }
  }, [addVoiceChip, keySet, play, speak, toast])

  const fail = useCallback((e: unknown) => {
    const x = e instanceof Error ? e : new Error(String(e))
    setErr(x)
    if (e instanceof ApiError && LANGUAGE_ERRORS.has(e.code)) { clearApiCache(); langs.reload() }
    if (e instanceof ApiError && e.code === 'NOT_CONFIGURED') return
    toast(x.message, 'bad')
  }, [langs, toast])

  const sendText = useCallback(async (t: string) => {
    const v = t.trim()
    if (!v || busy) return
    setBusy(true); setErr(null)
    try {
      const r = await api.textTurn(v, sessionRef.current, false, customerRef.current, stt)
      const botId = apply(r, 'text')
      void deliverVoice(r, botId)
    } catch (e) { fail(e) } finally { setBusy(false) }
  }, [apply, busy, deliverVoice, fail, stt])

  // ---------------------------------------------------------------- hand edits on the bill (no speech involved)
  const editLine = useCallback(async (productId: number, qty: number, how: 'set' | 'add' = 'set') => {
    setErr(null)
    setBusyLines((s) => new Set(s).add(productId))
    try {
      let sid = sessionRef.current
      if (!sid) { sid = (await api.newSession()).session_id; setSession(sid); sessionRef.current = sid }
      const r = await api.editCart(sid, productId, qty, how)
      setCart(r.cart); setPhase(r.phase); setAwaiting(r.awaiting); setPending(r.pending)
    } catch (e) {
      toast(e instanceof Error ? e.message : String(e), 'bad')
    } finally {
      setBusyLines((s) => { const n = new Set(s); n.delete(productId); return n })
    }
  }, [toast])
  const addProduct = (p: Product) => void editLine(p.id, 1, 'add')

  // ---------------------------------------------------------------- tap to talk (REST: Prisma STT + Timbre TTS)
  /** Sends one recording. The reply and the bill are drawn the moment they arrive; the voice follows (deliverVoice). A failure that may pass keeps the recording for "Try again". */
  const sendWav = useCallback(async (wav: Blob, mark: Mark) => {
    if (typeof navigator !== 'undefined' && navigator.onLine === false) {
      setRetry({ wav, mark })
      fail(new Error('This device is offline. Reconnect, then tap Try again: the recording is kept.'))
      setBusy(false)
      return
    }
    setBusy(true); setErr(null); setRetry(null)
    try {
      const r = await api.voiceTurn(wav, { language: stt, sessionId: sessionRef.current, speak: false, customerId: customerRef.current })
      const replyMs = Math.round(performance.now() - mark.endAt)
      const botId = apply(r, 'voice')
      void deliverVoice(r, botId, { ...mark, replyMs, bytes: wav.size })
    } catch (e) {
      if (transient(e)) setRetry({ wav, mark })
      fail(e)
    } finally { setBusy(false) }
  }, [apply, deliverVoice, fail, stt])

  const stopTap = useCallback(async (how: 'manual' | 'auto' = 'manual') => {
    if (autoStop.current) clearTimeout(autoStop.current)
    const rec = recRef.current
    if (!rec) return
    recRef.current = null
    const endAt = performance.now()
    setRecording(false); setBusy(true); setErr(null)
    let sent = false
    try {
      const { wav, seconds, peak, capturedSeconds } = await rec.stop()
      if (capturedSeconds < 0.4) { toast('That was too short. Tap, speak, then tap again to send.', 'info'); return }
      if (peak < 0.01) { toast('The microphone heard nothing. Check that the right microphone is selected.', 'bad'); return }
      sent = true
      await sendWav(wav, { endAt, capture: seconds * 1000, endpoint: how })
    } catch (e) { fail(e) } finally { if (!sent) setBusy(false) }
  }, [fail, sendWav, toast])
  stopTapRef.current = stopTap

  const startTap = useCallback(async () => {
    setErr(null); setRetry(null)
    const rec = new WavRecorder(setLevel, autoSend ? () => void stopTapRef.current('auto') : undefined)
    try {
      await rec.start()
      recRef.current = rec
      setRecording(true)
      autoStop.current = setTimeout(() => { toast('Stopped at 28 seconds, the limit for one message.', 'info'); void stopTapRef.current('manual') }, MAX_RECORD_S * 1000)
    } catch (e) { fail(e instanceof MicError ? new Error(e.message) : e) }
  }, [autoSend, fail, toast])

  const toggleAuto = (v: boolean) => { setAutoSend(v); try { localStorage.setItem(AUTO_KEY, v ? '1' : '0') } catch { /* private mode */ } }

  // ---------------------------------------------------------------- live stream (WebSocket proxy to Prisma streaming)
  const stopLive = useCallback(async () => {
    const ws = wsRef.current
    await micRef.current?.stop()
    micRef.current = null
    if (ws && ws.readyState === WebSocket.OPEN) { try { ws.send(JSON.stringify({ type: 'end' })) } catch { /* closing */ } }
    setTimeout(() => ws?.close(), 2500)
    setLiveState('off'); setLevel(0)
  }, [])

  const startLive = useCallback(async () => {
    setErr(null); setLiveState('connecting')
    const ws = new WebSocket(wsUrl(stt, sessionRef.current, speak && keySet, customerRef.current))
    wsRef.current = ws
    ws.onmessage = (ev) => {
      let m: { type: string; message?: string; code?: string; audio?: AudioInfo } & Partial<TurnResponse>
      try { m = JSON.parse(ev.data as string) } catch { return }
      if (m.type === 'ready') setLiveState('listening')
      else if (m.type === 'speech_start') setLiveState('hearing')
      else if (m.type === 'processing') { setLiveState('processing'); processingAt.current = performance.now() }
      else if (m.type === 'turn') {
        const r = m as TurnResponse
        const replyMs = processingAt.current ? Math.round(performance.now() - processingAt.current) : undefined
        const botId = apply(r, 'live')
        setLiveState('listening')
        const mark = { endAt: processingAt.current || performance.now(), capture: 0, endpoint: 'live' as const, replyMs }
        if (r.assistant_turn_id) markRef.current.set(r.assistant_turn_id, { ...mark, botId } as Mark & { replyMs?: number })
        if (speak && keySet && !r.audio) setPreparing(true)   // the voice follows as its own message
        else if (r.assistant_turn_id && replyMs !== undefined) void api.clientTiming(r.assistant_turn_id, { end_to_reply_ms: replyMs, endpoint: 'live' }).catch(() => undefined)
      } else if (m.type === 'audio') {
        setPreparing(false)
        const id = (m as { assistant_turn_id?: number }).assistant_turn_id
        const mk = id ? (markRef.current.get(id) as (Mark & { replyMs?: number; botId?: number }) | undefined) : undefined
        const a = m.audio
        if (mk?.botId && a) addVoiceChip(mk.botId, { tts_ms: a.tts_ms, cached: a.cached })
        if (a?.error) toast(a.error, 'info')
        const report = () => { if (id && mk) void api.clientTiming(id, { end_to_reply_ms: mk.replyMs, end_to_audio_ms: Math.round(performance.now() - mk.endAt), endpoint: 'live' }).catch(() => undefined) }
        if (a?.audio_url) play(a.audio_url, report); else report()
      }
      else if (m.type === 'error') { fail(Object.assign(new Error(m.message ?? 'Streaming error'), { code: m.code })); void stopLive() }
      else if (m.type === 'closed') setLiveState('off')
    }
    ws.onerror = () => { fail(new Error('Could not open the live connection. Is the backend running?')); setLiveState('off') }
    ws.onclose = (ev) => {
      void micRef.current?.stop(); micRef.current = null; setLiveState('off')
      if (ev.code === 4401) fail(new Error('Your session has ended. Sign in again to use live voice.'))   // refused at the handshake: no session
    }
    await new Promise<void>((res) => { ws.addEventListener('open', () => res(), { once: true }); ws.addEventListener('error', () => res(), { once: true }) })
    if (ws.readyState !== WebSocket.OPEN) return
    const mic = new MicCapture({
      onLevel: setLevel,
      onChunk: (c) => { if (ws.readyState === WebSocket.OPEN && !playing.current) ws.send(floatToPcm16(c).buffer) },
    })
    try { await mic.start(); micRef.current = mic } catch (e) { fail(e instanceof MicError ? new Error(e.message) : e); ws.close() }
  }, [addVoiceChip, apply, fail, keySet, play, speak, stopLive, stt, toast])

  const micAction = () => {
    if (mode === 'tap') return recording ? stopTap() : startTap()
    return liveState === 'off' ? startLive() : stopLive()
  }
  const micOn = mode === 'tap' ? recording : liveState !== 'off'
  const micDisabled = !keySet || (mode === 'tap' && busy && !recording)

  const next = () => {
    void stopLive()
    clearOpenSession(); setRestored(false); setRetry(null); setPreparing(false)
    setSession(null); sessionRef.current = null
    setMsgs([]); setCart(EMPTY_CART); setPending(null); setAwaiting(null); setPhase('collecting'); setOrder(null); setAlerts([]); setErr(null); setCustomer(null); setPaying(false); setPaySummary(null)
  }

  // After the payment window closes, read back what the server recorded; this screen never decides on its own that an order is paid.
  const closePayment = () => {
    setPaying(false)
    if (order) api.orderPayments(order.id).then((r) => setPaySummary(r.summary)).catch(() => undefined)
  }

  const canConfirm = cart.lines.length > 0 && !pending && phase !== 'completed' && phase !== 'cancelled' && !!session
  const confirm = async () => {
    if (!session) return
    setBusy(true); setErr(null)
    try { apply(await api.confirm(session, customerRef.current), 'text') } catch (e) { fail(e) } finally { setBusy(false) }
  }

  // ---------------------------------------------------------------- what the assistant is doing right now
  const orb: Orb = speaking ? 'speaking'
    : mode === 'live' && liveState === 'connecting' ? 'connecting'
    : recording || (mode === 'live' && liveState === 'listening') ? 'listening'
    : mode === 'live' && liveState === 'hearing' ? 'hearing'
    : preparing ? 'preparing'
    : busy || (mode === 'live' && liveState === 'processing') ? 'thinking' : 'idle'
  const micLabel = useMemo(() => {
    if (!keySet) return 'Add a Gnani key to use the microphone'
    if (mode === 'tap') return recording ? 'Stop and send' : busy ? 'Working on it' : 'Tap and speak'
    return { off: 'Start live listening', connecting: 'Connecting', listening: 'Stop live listening', hearing: 'Stop live listening', processing: 'Understanding' }[liveState]
  }, [busy, keySet, liveState, mode, recording])
  const stateText: Record<Orb, [string, string]> = {
    idle: [keySet ? 'Ready' : 'Typing only', keySet ? (mode === 'tap' ? 'Tap the microphone, say the order, tap again.' : 'Start live listening and just talk.') : 'Type an order below. The microphone needs a Gnani key.'],
    connecting: ['Connecting', 'Opening the live speech connection.'],
    listening: ['Listening', mode === 'tap' ? (autoSend ? 'Speak, then stop talking: it sends by itself. You can also tap to send now.' : 'Tap again when you are done.') : 'Speak normally. It sends when you pause.'],
    hearing: ['Hearing you', 'Keep going; it sends when you pause.'],
    thinking: [mode === 'tap' && recording === false && busy ? 'Working on it' : 'Understanding', 'Turning speech into text and matching items in your shop.'],
    preparing: ['Preparing the voice', 'The reply and the bill are on screen. The spoken reply follows in a moment.'],
    speaking: ['Replying', 'Playing the spoken reply.'],
  }
  const stepIdx = orb === 'listening' || orb === 'hearing' ? 0 : orb === 'thinking' ? 2 : orb === 'speaking' || orb === 'preparing' ? 3 : -1

  const orbIcon = orb === 'thinking' || orb === 'preparing' ? <span className="bars" aria-hidden><i /><i /><i /><i /><i /></span>
    : orb === 'speaking' ? <Icon name="speaker" size={34} /> : micOn ? <Icon name="stop" size={30} /> : <Icon name="mic" size={34} />

  return (
    <>
      <PageHeader title="Order desk" description="Take an order in Gujarati, Hindi, English, Marathi, Bengali, Tamil, Telugu, Kannada, Malayalam, Punjabi or Hinglish. The bill updates as the customer speaks, and you can change it by hand."
        meta={<Badge tone="plain">No order is saved until you confirm</Badge>} />
      <div className="stack">
        {!keySet && health.data && (
          <Note tone="warn">
            <b>Typing works now; the microphone needs a Gnani key.</b> Add GNANI_API_KEY in <Link to="/settings">Settings</Link> to turn on speech recognition and spoken replies.
          </Note>
        )}
        <div className="desk">
          <section className="card assistant" aria-label="Voice assistant">
            <div className="as-top">
              <LanguageSelector value={stt} onChange={setStt} options={langs.options} modes={langs.modes} disabled={recording || liveState !== 'off'} />
              <div className="field"><span className="label">Microphone</span>
                <Seg label="Microphone mode" value={mode} onChange={setMode} disabled={recording || liveState !== 'off'} options={[{ value: 'tap', label: 'Tap to talk' }, { value: 'live', label: 'Live stream' }]} /></div>
              {mode === 'tap' && <label className="check"><input type="checkbox" checked={autoSend} onChange={(e) => toggleAuto(e.target.checked)} disabled={recording} /> Send when I stop talking</label>}
              <label className="check right"><input type="checkbox" checked={speak} onChange={(e) => setSpeak(e.target.checked)} /> Speak replies</label>
            </div>

            <div className="as-stage">
              <div className={`orb-wrap ${orb === 'preparing' ? 'thinking' : orb}`} style={{ ['--lvl' as string]: 1 + level * 0.5 } as React.CSSProperties}>
                <i className="ring" /><i className="ring r2" />
                <button type="button" className={`orb ${orb === 'preparing' ? 'thinking' : orb}`} onClick={micAction} disabled={micDisabled} aria-label={micLabel} aria-pressed={micOn} title={micLabel}>{orbIcon}</button>
              </div>
              <div className="state-line" role="status" aria-live="polite">
                <b>{stateText[orb][0]}</b>
                <span className="muted small">{stateText[orb][1]}</span>
              </div>
              <div className="steps-row" aria-label="Progress">
                {STEPS.map((s, i) => <span key={s} className={`step${i === stepIdx || (orb === 'thinking' && i === 1 && mode === 'tap' && keySet) ? ' on' : i < stepIdx ? ' done' : ''}`}>{s}</span>)}
              </div>
            </div>

            <div className="talk" ref={talkRef} aria-live="polite" aria-label="Conversation">
              {msgs.length === 0 && <p className="muted small" style={{ margin: 'auto', textAlign: 'center' }}>The conversation shows here. Try a sample sentence below.</p>}
              {msgs.map((m) => (
                <div key={m.id} className={`msg ${m.who}`} lang={htmlLang(m.lang)}>
                  {m.text}
                  <div className="meta">{m.chips.map((c) => (<Badge key={c}>{c}</Badge>))}</div>
                </div>
              ))}
            </div>

            <div className="as-input">
              {restored && !order && <Note tone="info"><b>Your open bill was restored.</b> It was left open in this tab. <Button variant="link" onClick={next}>Start a new customer instead</Button></Note>}
              <ErrorNote error={err} />
              {retry && !busy && (
                <Note tone="warn">
                  <b>Your recording is kept.</b> The speech service did not answer, so nothing was added to the bill.{' '}
                  <Button variant="link" onClick={() => void sendWav(retry.wav, { ...retry.mark, endAt: performance.now() })}>Try again</Button>{' '}or{' '}
                  <Button variant="link" onClick={() => { setRetry(null); document.getElementById('typed')?.focus() }}>type it instead</Button>.
                </Note>
              )}
              <QuickReplies pending={pending} awaiting={awaiting} onSend={sendText} disabled={busy || phase === 'completed'} />
              <form className="field" onSubmit={(e) => { e.preventDefault(); void sendText(text); setText('') }}>
                <label htmlFor="typed">Or type the order</label>
                <div className="row nowrap">
                  <input id="typed" type="text" value={text} onChange={(e) => setText(e.target.value)} placeholder="e.g. 2 kilo chawal aur 1 litre doodh" autoComplete="off" maxLength={600} disabled={phase === 'completed'} />
                  <Button type="submit" disabled={busy || !text.trim() || phase === 'completed'} icon="arrowRight">Send</Button>
                </div>
              </form>
              <div className="quick" aria-label="Sample sentences">
                {sampleSentences.map((s) => (<button key={s} type="button" lang={htmlLangOf(s)} onClick={() => sendText(s)} disabled={busy || phase === 'completed'}>{s}</button>))}
              </div>
            </div>
          </section>

          <div className="stack">
            {order && (
              <section className="card confirmed" aria-label="Order confirmed">
                <div className="row nowrap">
                  <span className="tick"><Icon name="check" size={20} /></span>
                  <div className="grow"><b style={{ fontSize: 16 }}>Order confirmed</b><div className="muted small">{order.code} · {rupees(order.total_paise)} · stock has been reduced</div></div>
                </div>
                {alerts.length > 0 && (
                  <Note tone="warn"><b>Running low:</b>{' '}{alerts.map((a) => `${a.name} (${a.severity === 'out' ? 'finished' : `${a.stock} ${a.unit} left`})`).join(', ')}. <Link to="/inventory?status=low">Restock</Link></Note>
                )}
                {paySummary && paySummary.status !== 'none' && (
                  <div className="row tight" role="status"><span className="muted small">Payment</span><PayStatusBadge status={paySummary.status} />
                    {paySummary.paid_paise > 0 && <span className="small">{rupees(paySummary.paid_paise)}</span>}</div>
                )}
                <div className="row">
                  {(!paySummary || !['paid', 'partially_refunded', 'refunded'].includes(paySummary.status)) && <Button icon="wallet" onClick={() => setPaying(true)}>{paySummary?.status === 'pending' ? 'Continue payment' : 'Take payment'}</Button>}
                  <Button variant="accent" onClick={next}>Next customer</Button><Link className="btn secondary" to={`/orders?open=${order.id}`}>View order</Link>
                </div>
              </section>
            )}
            {paying && order && <PaymentDialog orderId={order.id} onClose={closePayment} />}
            <Bill cart={cart} lang={displayLang} customer={customer} onCustomer={setCustomer} onSetQty={(id, q) => void editLine(id, q)} onAdd={addProduct}
                  busyLines={busyLines} locked={!!order}
                  note={pending ? <Note tone="info">Answer the assistant's question first, then confirm.</Note> : undefined}
                  footer={order ? <span className="muted small">Saved. Start the next customer when ready.</span> : (
                    <>
                      <Button variant="secondary" onClick={next} disabled={busy || (!session && !msgs.length)}>Clear</Button>
                      <Button variant="accent" size="lg" onClick={confirm} disabled={!canConfirm || busy} loading={busy && canConfirm} title={pending ? 'Answer the question first' : undefined}>Confirm order</Button>
                    </>
                  )} />
            {phase === 'cancelled' && <Note tone="info">This order was cancelled. Nothing was saved. <Button variant="link" onClick={next}>Start again</Button></Note>}
          </div>
        </div>
      </div>
    </>
  )
}
