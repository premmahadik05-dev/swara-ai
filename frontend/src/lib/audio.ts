/** Microphone capture and conversion to what Gnani Prisma wants: 16 kHz, mono, 16-bit PCM. */

export const TARGET_RATE = 16000

/** Streaming linear-interpolation resampler (keeps its fractional position between chunks). */
export class Resampler {
  private pos = 0
  private last = 0
  private readonly ratio: number
  constructor(from: number, to: number = TARGET_RATE) {
    this.ratio = from / to
  }
  process(input: Float32Array): Float32Array {
    if (this.ratio === 1) return input
    const out: number[] = []
    // sample index -1 is `last` (carried from the previous chunk)
    while (this.pos < input.length) {
      const i = Math.floor(this.pos)
      const frac = this.pos - i
      const a = i < 0 ? this.last : input[i]
      const b = i + 1 < input.length ? input[i + 1] : input[input.length - 1]
      out.push(a + (b - a) * frac)
      this.pos += this.ratio
    }
    this.pos -= input.length
    this.last = input.length ? input[input.length - 1] : this.last
    return Float32Array.from(out)
  }
}

export function resample(input: Float32Array, from: number, to: number = TARGET_RATE): Float32Array {
  return new Resampler(from, to).process(input)
}

export function floatToPcm16(input: Float32Array): Int16Array {
  const out = new Int16Array(input.length)
  for (let i = 0; i < input.length; i++) {
    const s = Math.max(-1, Math.min(1, input[i]))
    out[i] = s < 0 ? Math.round(s * 0x8000) : Math.round(s * 0x7fff)
  }
  return out
}

export function encodeWav(samples: Float32Array, sampleRate: number = TARGET_RATE): Blob {
  const pcm = floatToPcm16(samples)
  const buf = new ArrayBuffer(44 + pcm.length * 2)
  const v = new DataView(buf)
  const str = (o: number, s: string) => { for (let i = 0; i < s.length; i++) v.setUint8(o + i, s.charCodeAt(i)) }
  str(0, 'RIFF'); v.setUint32(4, 36 + pcm.length * 2, true); str(8, 'WAVE'); str(12, 'fmt ')
  v.setUint32(16, 16, true); v.setUint16(20, 1, true); v.setUint16(22, 1, true)
  v.setUint32(24, sampleRate, true); v.setUint32(28, sampleRate * 2, true); v.setUint16(32, 2, true); v.setUint16(34, 16, true)
  str(36, 'data'); v.setUint32(40, pcm.length * 2, true)
  new Int16Array(buf, 44).set(pcm)
  return new Blob([buf], { type: 'audio/wav' })
}

/** Window length used to judge loud versus quiet: 20 ms of 16 kHz audio. */
const WIN = 320
const PAD_S = 0.25   // quiet audio kept before and after the speech, so a soft first or last syllable is never clipped

function windowLevels(x: Float32Array): number[] {
  const out: number[] = []
  for (let i = 0; i < x.length; i += WIN) out.push(rms(x.subarray(i, Math.min(x.length, i + WIN))))
  return out
}

/** The level that separates "someone is talking" from the room: a few times the quietest fifth of the recording, and never below a small floor. */
export function speechThreshold(levels: number[], floorMin = 0.012, factor = 3): number {
  if (!levels.length) return floorMin
  const sorted = [...levels].sort((a, b) => a - b)
  const floor = sorted[Math.floor(sorted.length * 0.2)] ?? sorted[0]
  return Math.max(floorMin, floor * factor)
}

/**
 * Cuts the quiet stretch before the first word and after the last one (keeping 250 ms of padding each side), so less audio is uploaded and
 * Prisma has less to listen to. Pauses inside the order are left alone. If nothing in the recording rises above the room level it is returned
 * unchanged, so a quiet voice is never trimmed to nothing.
 */
export function trimSilence(x: Float32Array, rate = TARGET_RATE): Float32Array {
  const levels = windowLevels(x)
  const thr = speechThreshold(levels)
  const first = levels.findIndex((l) => l > thr)
  if (first < 0) return x
  let last = levels.length - 1
  while (last > first && levels[last] <= thr) last--
  const pad = Math.round(PAD_S * rate)
  const from = Math.max(0, first * WIN - pad)
  const to = Math.min(x.length, (last + 1) * WIN + pad)
  return from === 0 && to === x.length ? x : x.slice(from, to)
}

export interface EndpointOptions {
  /** quiet time after speech that counts as "finished"; long enough to allow a breath between "two kilo rice" and "one litre milk" */
  hangoverS?: number
  /** speech heard before an end can be declared (ignores a cough or a tap on the desk) */
  minSpeechS?: number
}

/**
 * Decides, from the live level of the microphone, when a person has finished speaking. Feed it every captured chunk; it answers true once, when
 * speech was heard and then the room stayed quiet for the hangover time. It learns the room level from the first 300 ms and follows slow changes,
 * so a noisy shop needs a voice clearly above the noise, and a steady hum does not keep it open forever. The microphone can always be stopped by
 * hand, and the recorder has its own length limit, so this only ever makes sending faster.
 */
export class EndpointDetector {
  private floor = 0
  private heard = 0       // seconds of speech so far
  private quiet = 0       // seconds of quiet since the last speech
  private elapsed = 0
  private pending: number[] = []
  private pendingN = 0
  private calibrated = false
  private fired = false
  private readonly hangover: number
  private readonly minSpeech: number
  constructor(o: EndpointOptions = {}, private rate = TARGET_RATE) {
    this.hangover = o.hangoverS ?? 1.1
    this.minSpeech = o.minSpeechS ?? 0.3
  }

  get speechSeconds() { return this.heard }
  get speaking() { return this.heard >= this.minSpeech && this.quiet < 0.25 }

  /** Returns true exactly once: the moment the end of speech is decided. */
  feed(chunk: Float32Array): boolean {
    if (this.fired || !chunk.length) return false
    this.pending.push(rms(chunk) ** 2 * chunk.length)
    this.pendingN += chunk.length
    if (this.pendingN < WIN) return false
    const level = Math.sqrt(this.pending.reduce((a, b) => a + b, 0) / this.pendingN)
    const dt = this.pendingN / this.rate
    this.pending = []; this.pendingN = 0
    this.elapsed += dt
    if (!this.calibrated) {
      this.floor = this.floor ? Math.min(this.floor, level) : level
      if (this.elapsed >= 0.3) this.calibrated = true
      return false
    }
    const loud = Math.max(0.015, this.floor * 3)
    if (level > loud) { this.heard += dt; this.quiet = 0 }
    else {
      if (this.heard > 0) this.quiet += dt
      if (level < loud * 0.6) this.floor = this.floor * 0.95 + level * 0.05   // follow the room, never the voice
    }
    if (this.heard >= this.minSpeech && this.quiet >= this.hangover) { this.fired = true; return true }
    return false
  }
}

export function rms(x: Float32Array): number {
  if (!x.length) return 0
  let s = 0
  for (let i = 0; i < x.length; i++) s += x[i] * x[i]
  return Math.sqrt(s / x.length)
}

/** Decode any browser-readable audio file (wav/mp3/ogg/m4a) into 16 kHz mono samples. */
export async function decodeToMono16k(file: Blob): Promise<Float32Array> {
  const ctx = new AudioContext()
  try {
    const ab = await ctx.decodeAudioData(await file.arrayBuffer())
    const ch0 = ab.getChannelData(0)
    let mono = ch0
    if (ab.numberOfChannels > 1) {
      mono = new Float32Array(ch0.length)
      for (let c = 0; c < ab.numberOfChannels; c++) { const d = ab.getChannelData(c); for (let i = 0; i < d.length; i++) mono[i] += d[i] / ab.numberOfChannels }
    }
    return resample(mono, ab.sampleRate)
  } finally {
    void ctx.close()
  }
}

const WORKLET = `
class Tap extends AudioWorkletProcessor {
  process(inputs) { const c = inputs[0] && inputs[0][0]; if (c && c.length) this.port.postMessage(c.slice(0)); return true }
}
registerProcessor('tap', Tap)
`

export type MicErrorKind = 'denied' | 'no-device' | 'unsupported' | 'other'
export class MicError extends Error {
  kind: MicErrorKind
  constructor(kind: MicErrorKind, message: string) { super(message); this.kind = kind }
}

export interface MicOptions {
  /** receives 16 kHz mono float chunks as they are captured */
  onChunk: (pcm16k: Float32Array) => void
  /** 0..1 loudness for the UI meter */
  onLevel?: (level: number) => void
}

export class MicCapture {
  private ctx?: AudioContext
  private stream?: MediaStream
  private node?: AudioNode
  private sink?: GainNode
  private resampler?: Resampler
  constructor(private opts: MicOptions) {}

  async start(): Promise<void> {
    if (!navigator.mediaDevices?.getUserMedia) throw new MicError('unsupported', 'This browser cannot record audio. Use Chrome or Edge on localhost or https.')
    try {
      this.stream = await navigator.mediaDevices.getUserMedia({ audio: { channelCount: 1, echoCancellation: true, noiseSuppression: false, autoGainControl: true } })
    } catch (e) {
      const name = (e as DOMException).name
      if (name === 'NotAllowedError' || name === 'SecurityError') throw new MicError('denied', 'Microphone access was blocked. Allow it in the address bar, then try again.')
      if (name === 'NotFoundError' || name === 'OverconstrainedError') throw new MicError('no-device', 'No microphone found. Plug one in or type the order instead.')
      throw new MicError('other', `Could not start the microphone (${name}).`)
    }
    this.ctx = new AudioContext()
    if (this.ctx.state === 'suspended') await this.ctx.resume()
    this.resampler = new Resampler(this.ctx.sampleRate)
    const src = this.ctx.createMediaStreamSource(this.stream)
    const handle = (chunk: Float32Array) => {
      this.opts.onLevel?.(Math.min(1, rms(chunk) * 6))
      this.opts.onChunk(this.resampler!.process(chunk))
    }
    this.sink = this.ctx.createGain()
    this.sink.gain.value = 0 // keep the graph alive without playing the mic back
    this.sink.connect(this.ctx.destination)
    try {
      const url = URL.createObjectURL(new Blob([WORKLET], { type: 'application/javascript' }))
      await this.ctx.audioWorklet.addModule(url)
      URL.revokeObjectURL(url)
      const n = new AudioWorkletNode(this.ctx, 'tap')
      n.port.onmessage = (e) => handle(e.data as Float32Array)
      src.connect(n).connect(this.sink)
      this.node = n
    } catch {
      // Older browsers: ScriptProcessor fallback
      const sp = this.ctx.createScriptProcessor(4096, 1, 1)
      sp.onaudioprocess = (e) => handle(new Float32Array(e.inputBuffer.getChannelData(0)))
      src.connect(sp).connect(this.sink)
      this.node = sp
    }
  }

  async stop(): Promise<void> {
    this.node?.disconnect()
    this.sink?.disconnect()
    this.stream?.getTracks().forEach((t) => t.stop())
    await this.ctx?.close().catch(() => undefined)
    this.node = this.sink = this.stream = this.ctx = undefined
    this.opts.onLevel?.(0)
  }
}

/** Records one utterance as a 16 kHz mono WAV (Gnani REST limit is 30 s; callers should auto-stop). */
export class WavRecorder {
  private chunks: Float32Array[] = []
  private mic: MicCapture
  private peak = 0
  private detector?: EndpointDetector
  /** milliseconds since the recording started, when the end of speech was decided (null if it never was) */
  endedAt: number | null = null
  private t0 = 0
  /** `onEndOfSpeech` is called once when the person has stopped talking; leave it out to stop only by hand. */
  constructor(onLevel?: (l: number) => void, private onEndOfSpeech?: () => void) {
    if (onEndOfSpeech) this.detector = new EndpointDetector()
    this.mic = new MicCapture({
      onChunk: (c) => {
        this.chunks.push(c)
        for (let i = 0; i < c.length; i++) this.peak = Math.max(this.peak, Math.abs(c[i]))
        if (this.detector?.feed(c)) { this.endedAt = performance.now() - this.t0; this.onEndOfSpeech?.() }
      },
      onLevel,
    })
  }
  start() { this.chunks = []; this.peak = 0; this.endedAt = null; if (this.onEndOfSpeech) this.detector = new EndpointDetector(); this.t0 = performance.now(); return this.mic.start() }
  get seconds() { return this.chunks.reduce((n, c) => n + c.length, 0) / TARGET_RATE }
  get heardSpeech() { return (this.detector?.speechSeconds ?? 0) > 0 }
  async stop(): Promise<{ wav: Blob; seconds: number; peak: number; capturedSeconds: number }> {
    await this.mic.stop()
    const total = this.chunks.reduce((n, c) => n + c.length, 0)
    const all = new Float32Array(total)
    let o = 0
    for (const c of this.chunks) { all.set(c, o); o += c.length }
    this.chunks = []
    const trimmed = trimSilence(all)
    return { wav: encodeWav(trimmed), seconds: trimmed.length / TARGET_RATE, peak: this.peak, capturedSeconds: total / TARGET_RATE }
  }
}
