import { useEffect, useId, useRef, useState } from 'react'
import type { Lang, SttChoice } from '../types'
import { liveSummary, understandingNote, htmlLang } from '../lib/languages'
import type { LangOption } from '../lib/useLanguages'
import type { LanguageMode } from '../types'
import { Badge } from './ui'
import { Icon } from './Icons'

const LIVE_TONE = { verified: 'ok', partial: 'info', failed: 'bad', simulated: 'warn', none: 'plain' } as const

/**
 * The language the customer speaks. One button shows the current choice; it opens a short list of every language the server offers, each
 * with its Gnani codes and an honest status. "Live checked" appears only when a real run against Gnani passed; otherwise the language says
 * "Not verified live". A language that is switched off is listed but cannot be picked, and Auto-detect says why it is unavailable.
 */
export function LanguageSelector({ value, onChange, options, modes, disabled, label = 'Customer speaks' }: {
  value: SttChoice
  onChange: (v: SttChoice) => void
  options: LangOption[]
  modes: LanguageMode[]
  disabled?: boolean
  label?: string
}) {
  const [open, setOpen] = useState(false)
  const [peek, setPeek] = useState<SttChoice | null>(null)
  const box = useRef<HTMLDivElement>(null)
  const trigger = useRef<HTMLButtonElement>(null)
  const id = useId()
  const auto = modes.find((m) => m.key === 'auto')
  const current = value === 'auto' ? null : options.find((o) => o.key === value)
  const shown = peek ?? value
  const shownOpt = shown === 'auto' ? null : options.find((o) => o.key === shown)

  useEffect(() => {
    if (!open) return
    const onDown = (e: MouseEvent) => { if (box.current && !box.current.contains(e.target as Node)) setOpen(false) }
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') { setOpen(false); trigger.current?.focus() } }
    document.addEventListener('mousedown', onDown)
    document.addEventListener('keydown', onKey)
    return () => { document.removeEventListener('mousedown', onDown); document.removeEventListener('keydown', onKey) }
  }, [open])
  useEffect(() => { if (disabled) setOpen(false) }, [disabled])

  const pick = (v: SttChoice) => { onChange(v); setPeek(null); setOpen(false); trigger.current?.focus() }
  const triggerTitle = value === 'auto' ? 'Auto-detect' : current ? current.name : value
  const summary = current?.info ? liveSummary(current.info.verification) : null

  return (
    <div className="lang-sel" ref={box}>
      <span className="label" id={`${id}-l`}>{label}</span>
      <button ref={trigger} type="button" className="lang-trigger" disabled={disabled} aria-haspopup="dialog" aria-expanded={open} aria-labelledby={`${id}-l ${id}-t`}
              onClick={() => setOpen((o) => !o)}>
        <span className="lang-name" id={`${id}-t`}>
          <b lang={current ? htmlLang(current.key) : 'en'}>{current ? current.native : 'Auto-detect'}</b>
          {current && current.native !== current.name && <span className="muted"> {current.name}</span>}
        </span>
        {current?.info && <span className="lang-code mono">{current.info.stt_code}</span>}
        <Icon name={open ? 'chevronUp' : 'chevronDown'} size={16} />
        <span className="sr-only">{triggerTitle}</span>
      </button>
      {current && (
        <p className="lang-caption muted small">
          {current.info
            ? <>Speech: {current.info.stt_code} (Prisma) · Voice: {current.info.voice} (Timbre){summary ? ` · ${summary.label}` : ''}</>
            : 'Details unavailable: the server could not be reached.'}
        </p>
      )}
      {open && (
        <div className="lang-pop" role="dialog" aria-label="Choose the language the customer speaks">
          <div role="radiogroup" aria-label="Languages" className="lang-grid">
            {options.map((o) => {
              const s = o.info ? liveSummary(o.info.verification) : null
              return (
                <label key={o.key} className={`lang-opt${value === o.key ? ' on' : ''}${o.enabled ? '' : ' off'}`}
                       onMouseEnter={() => setPeek(o.key)} onMouseLeave={() => setPeek(null)}>
                  <input type="radio" name={`${id}-lang`} value={o.key} checked={value === o.key} disabled={!o.enabled}
                         onChange={() => pick(o.key as Lang)} onFocus={() => setPeek(o.key)} onBlur={() => setPeek(null)} />
                  <span className="lang-opt-main">
                    <b lang={htmlLang(o.key)}>{o.native}</b>
                    <span className="muted small">{o.native !== o.name ? o.name : o.script}{o.info ? ` · ${o.info.stt_code}` : ''}</span>
                  </span>
                  <span className="lang-opt-badges">
                    {!o.enabled ? <Badge tone="plain">Switched off</Badge>
                      : s ? <Badge tone={LIVE_TONE[s.state]} title={s.detail}>{s.label}</Badge> : null}
                    {o.enabled && o.info?.nlu_status === 'authored' && <Badge tone="plain" title={understandingNote({ name: o.name, nlu_status: 'authored' })}>New in 2.3</Badge>}
                  </span>
                </label>
              )
            })}
            <label className={`lang-opt${value === 'auto' ? ' on' : ''}${auto?.available ? '' : ' off'}`} onMouseEnter={() => setPeek('auto')} onMouseLeave={() => setPeek(null)}>
              <input type="radio" name={`${id}-lang`} value="auto" checked={value === 'auto'} disabled={!auto?.available} onChange={() => pick('auto')} onFocus={() => setPeek('auto')} onBlur={() => setPeek(null)} />
              <span className="lang-opt-main"><b>Auto-detect</b><span className="muted small">{auto?.available ? 'Prisma v3.0 picks the language' : (auto?.reason ?? 'Not available')}</span></span>
              <span className="lang-opt-badges">{!auto?.available && <Badge tone="plain">Unavailable</Badge>}</span>
            </label>
          </div>
          <div className="lang-detail" aria-live="polite">
            {shownOpt ? (
              <>
                <p><b>{shownOpt.name}</b>{shownOpt.info ? ` · speech ${shownOpt.info.stt_code}, voice ${shownOpt.info.voice} (${shownOpt.info.tts_depth === 'deep' ? 'documented in depth by Gnani' : 'supported by Gnani'})` : ''}</p>
                {shownOpt.info && <p className="muted small">{liveSummary(shownOpt.info.verification).detail}</p>}
                {shownOpt.info?.stt_note && <p className="muted small">{shownOpt.info.stt_note}</p>}
                {shownOpt.info && <p className="muted small">{understandingNote({ name: shownOpt.name, nlu_status: shownOpt.info.nlu_status })}</p>}
              </>
            ) : (
              <p className="muted small">{auto?.available ? 'Auto-detect lets Gnani Prisma v3.0 choose among the supported languages for each recording.' : (auto?.reason ?? '')}</p>
            )}
          </div>
        </div>
      )}
    </div>
  )
}
