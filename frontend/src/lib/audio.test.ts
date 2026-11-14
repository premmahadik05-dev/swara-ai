import { describe, expect, it } from 'vitest'
import { Resampler, encodeWav, floatToPcm16, resample, rms } from './audio'

describe('audio utilities', () => {
  it('encodes a 16-bit mono PCM WAV header correctly', async () => {
    const wav = encodeWav(new Float32Array(1600), 16000)
    const v = new DataView(await wav.arrayBuffer())
    const tag = (o: number) => String.fromCharCode(v.getUint8(o), v.getUint8(o + 1), v.getUint8(o + 2), v.getUint8(o + 3))
    expect(tag(0)).toBe('RIFF')
    expect(tag(8)).toBe('WAVE')
    expect(v.getUint16(20, true)).toBe(1) // PCM
    expect(v.getUint16(22, true)).toBe(1) // mono
    expect(v.getUint32(24, true)).toBe(16000)
    expect(v.getUint16(34, true)).toBe(16)
    expect(v.getUint32(40, true)).toBe(3200)
    expect(wav.size).toBe(44 + 3200)
  })

  it('clips and scales float samples to int16', () => {
    const p = floatToPcm16(Float32Array.from([0, 1, -1, 2, -2, 0.5]))
    expect(Array.from(p)).toEqual([0, 32767, -32768, 32767, -32768, 16384])
  })

  it('downsamples 48 kHz to 16 kHz with the right length and preserves a low tone', () => {
    const n = 48000
    const x = new Float32Array(n)
    for (let i = 0; i < n; i++) x[i] = Math.sin((2 * Math.PI * 200 * i) / 48000)
    const y = resample(x, 48000, 16000)
    expect(Math.abs(y.length - 16000)).toBeLessThanOrEqual(2)
    expect(rms(y)).toBeGreaterThan(0.68)
    expect(rms(y)).toBeLessThan(0.74)
  })

  it('chunked resampling equals one-shot resampling (no seams at chunk edges)', () => {
    const x = Float32Array.from({ length: 4410 }, (_, i) => Math.sin(i / 7))
    const one = resample(x, 44100, 16000)
    const r = new Resampler(44100, 16000)
    const parts = [x.slice(0, 1000), x.slice(1000, 2345), x.slice(2345)]
    const chunked = Float32Array.from(parts.flatMap((p) => Array.from(r.process(p))))
    expect(Math.abs(chunked.length - one.length)).toBeLessThanOrEqual(1)
    for (let i = 0; i < Math.min(one.length, chunked.length) - 1; i++) expect(chunked[i]).toBeCloseTo(one[i], 3)
  })

  it('passes audio through unchanged at 16 kHz', () => {
    const x = Float32Array.from([0.1, 0.2, 0.3])
    expect(Array.from(resample(x, 16000, 16000))).toEqual(Array.from(x))
  })
})

// ---------------------------------------------------------------------------------------------------- silence trimming and end of speech
import { EndpointDetector, speechThreshold, trimSilence } from './audio'

const RATE = 16000
function seeded(seed: number) { let a = seed; return () => { a = (a * 1664525 + 1013904223) % 4294967296; return a / 4294967296 } }
/** a steady "voice": a 200 Hz tone with the given peak amplitude */
function voice(seconds: number, amp = 0.2): Float32Array { const n = Math.round(seconds * RATE); const o = new Float32Array(n); for (let i = 0; i < n; i++) o[i] = amp * Math.sin((2 * Math.PI * 200 * i) / RATE); return o }
/** the room: low random noise */
function room(seconds: number, amp = 0.004, seed = 7): Float32Array { const r = seeded(seed); const n = Math.round(seconds * RATE); const o = new Float32Array(n); for (let i = 0; i < n; i++) o[i] = (r() - 0.5) * 2 * amp; return o }
function cat(...parts: Float32Array[]): Float32Array { const o = new Float32Array(parts.reduce((n, p) => n + p.length, 0)); let k = 0; for (const p of parts) { o.set(p, k); k += p.length } return o }
function feedAll(d: EndpointDetector, x: Float32Array, step = 512): number | null {
  for (let i = 0; i < x.length; i += step) if (d.feed(x.subarray(i, Math.min(x.length, i + step)))) return (i + step) / RATE
  return null
}

describe('trimSilence', () => {
  it('cuts the quiet before and after the speech but keeps 250 ms of padding', () => {
    const x = cat(room(2.0), voice(1.0), room(3.0))
    const t = trimSilence(x)
    const seconds = t.length / RATE
    expect(seconds).toBeGreaterThan(1.0 + 0.45)   // speech plus about 0.25 s each side
    expect(seconds).toBeLessThan(1.0 + 0.6)
  })
  it('never cuts a pause inside the order', () => {
    const x = cat(room(1.0), voice(0.8), room(0.7), voice(0.8), room(1.0))
    const t = trimSilence(x)
    expect(t.length / RATE).toBeGreaterThan(0.8 + 0.7 + 0.8)
  })
  it('returns a recording with no speech unchanged', () => {
    const x = room(2.0)
    expect(trimSilence(x)).toBe(x)
  })
  it('does not cut a quiet voice to nothing', () => {
    const x = cat(room(1.0, 0.002), voice(1.0, 0.05), room(1.0, 0.002))
    expect(trimSilence(x).length / RATE).toBeGreaterThan(1.0)
  })
  it('returns the same array when there is nothing to trim', () => {
    const x = voice(1.0)
    expect(trimSilence(x)).toBe(x)
  })
  it('uses a floor so a silent-but-digital-zero start does not make the threshold zero', () => {
    expect(speechThreshold([0, 0, 0, 0, 0])).toBeGreaterThan(0)
  })
})

describe('EndpointDetector', () => {
  it('says the person has finished after speech and then about a second of quiet', () => {
    const at = feedAll(new EndpointDetector(), cat(room(0.5), voice(1.5), room(3.0)))
    expect(at).not.toBeNull()
    expect(at!).toBeGreaterThan(0.5 + 1.5 + 1.0)   // not before the hangover has passed
    expect(at!).toBeLessThan(0.5 + 1.5 + 1.4)
  })
  it('does not end before anyone has spoken', () => {
    expect(feedAll(new EndpointDetector(), room(10))).toBeNull()
  })
  it('waits through a breath between two items', () => {
    const x = cat(room(0.5), voice(1.0), room(0.6), voice(1.0), room(3.0))
    const at = feedAll(new EndpointDetector(), x)
    expect(at!).toBeGreaterThan(0.5 + 1.0 + 0.6 + 1.0 + 1.0)   // ended after the second item, not in the gap
  })
  it('ignores a very short noise such as a tap on the counter', () => {
    expect(feedAll(new EndpointDetector(), cat(room(0.5), voice(0.1, 0.5), room(4)))).toBeNull()
  })
  it('works in a noisy shop: a voice clearly above a steady hum ends after the hum alone', () => {
    const hum = (s: number) => room(s, 0.03, 3)
    const at = feedAll(new EndpointDetector(), cat(hum(0.6), voice(1.2, 0.35), hum(3)))
    expect(at).not.toBeNull()
  })
  it('fires once only', () => {
    const d = new EndpointDetector()
    const x = cat(room(0.5), voice(1.5), room(3.0))
    expect(feedAll(d, x)).not.toBeNull()
    expect(d.feed(room(0.2))).toBe(false)
  })
})
