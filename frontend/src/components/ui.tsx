import { forwardRef, useEffect, useId, useState, type ButtonHTMLAttributes, type ReactNode } from 'react'
import { Link } from 'react-router-dom'
import type { ApiError } from '../api/client'
import { Icon, type IconName } from './Icons'

/* ------------------------------------------------------------------ actions */
type Variant = 'primary' | 'secondary' | 'ghost' | 'danger' | 'accent' | 'solid-danger' | 'link'
interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: Variant
  size?: 'sm' | 'md' | 'lg'
  icon?: IconName
  loading?: boolean
  /** icon-only button: `aria-label` is then required */
  iconOnly?: boolean
}
export const Button = forwardRef<HTMLButtonElement, ButtonProps>(function Button(
  { variant = 'primary', size = 'md', icon, loading, iconOnly, className = '', children, disabled, type = 'button', ...rest }, ref,
) {
  const cls = ['btn', variant === 'secondary' ? 'secondary' : variant === 'primary' ? '' : variant, size === 'sm' ? 'small' : size === 'lg' ? 'large' : '', iconOnly ? 'icon' : '', className].filter(Boolean).join(' ')
  return (
    <button ref={ref} type={type} className={cls} disabled={disabled || loading} aria-busy={loading || undefined} {...rest}>
      {loading ? <span className="spinner" aria-hidden /> : icon ? <Icon name={icon} size={size === 'sm' ? 15 : 17} /> : null}
      {children}
    </button>
  )
})

export function Badge({ tone, children, title, dot, className = '' }: { tone?: 'ok' | 'warn' | 'bad' | 'info' | 'accent' | 'plain'; children: ReactNode; title?: string; dot?: boolean; className?: string }) {
  return <span className={`badge ${tone ?? ''} ${className}`.trim()} title={title}>{dot && <i className="dot" aria-hidden />}{children}</span>
}
/** Older pages call this `Chip kind=...`. Same component. */
export function Chip({ kind, children, title }: { kind?: 'ok' | 'warn' | 'bad' | 'info' | 'accent'; children: ReactNode; title?: string }) {
  return <Badge tone={kind} title={title}>{children}</Badge>
}

/* ------------------------------------------------------------------ structure */
export function PageHeader({ title, description, actions, meta }: { title: string; description?: ReactNode; actions?: ReactNode; meta?: ReactNode }) {
  return (
    <header className="page-head">
      <div className="t">
        <h1>{title}</h1>
        {description && <p className="muted">{description}</p>}
        {meta && <div className="row tight" style={{ marginTop: 8 }}>{meta}</div>}
      </div>
      {actions && <div className="row page-actions">{actions}</div>}
    </header>
  )
}

export function Card({ title, description, actions, children, flush, className = '', as: Tag = 'section', label }: {
  title?: ReactNode; description?: ReactNode; actions?: ReactNode; children?: ReactNode; flush?: boolean; className?: string; as?: 'section' | 'div' | 'aside'; label?: string
}) {
  const id = useId()
  return (
    <Tag className={`card ${className}`.trim()} aria-labelledby={title ? id : undefined} aria-label={!title ? label : undefined}>
      {(title || actions) && (
        <div className="card-head">
          <div className="t">{title && <h2 id={id} className="h3">{title}</h2>}{description && <p>{description}</p>}</div>
          {actions && <div className="row tight">{actions}</div>}
        </div>
      )}
      <div className={`card-body${flush ? ' flush' : ''}`}>{children}</div>
    </Tag>
  )
}

export function Field({ label, hint, error, children, htmlFor }: { label: string; hint?: ReactNode; error?: string | null; children: ReactNode; htmlFor?: string }) {
  return (
    <div className="field">
      <label htmlFor={htmlFor}>{label}</label>
      {children}
      {error ? <span className="err" role="alert">{error}</span> : hint ? <span className="hint">{hint}</span> : null}
    </div>
  )
}

export function SearchBox({ value, onChange, placeholder, label, id, autoFocus }: { value: string; onChange: (v: string) => void; placeholder?: string; label: string; id?: string; autoFocus?: boolean }) {
  return (
    <div className="search">
      <Icon name="search" size={16} />
      <input id={id} type="search" role="searchbox" aria-label={label} value={value} placeholder={placeholder} autoFocus={autoFocus} autoComplete="off"
             onChange={(e) => onChange(e.target.value)} />
      {value && <button type="button" className="btn ghost icon small clear" aria-label="Clear search" onClick={() => onChange('')}><Icon name="x" size={14} /></button>}
    </div>
  )
}

/** Single-choice segmented control. Counts are optional and come from the server, not from the visible page. */
export function Seg<T extends string>({ value, onChange, options, label, disabled }: {
  value: T; onChange: (v: T) => void; options: { value: T; label: string; count?: number }[]; label: string; disabled?: boolean
}) {
  return (
    <div className="seg" role="group" aria-label={label}>
      {options.map((o) => (
        <button key={o.value} type="button" aria-pressed={value === o.value} disabled={disabled} onClick={() => onChange(o.value)}>
          {o.label}{o.count !== undefined && <span className="count">{o.count.toLocaleString('en-IN')}</span>}
        </button>
      ))}
    </div>
  )
}

export function SortTh({ label, field, sort, onSort, className }: { label: string; field: string; sort: string; onSort: (s: string) => void; className?: string }) {
  const active = sort === field
  return (
    <th className={className} aria-sort={active ? 'ascending' : 'none'}>
      <button type="button" onClick={() => onSort(field)}>{label}{active && <Icon name="sortUp" size={13} />}</button>
    </th>
  )
}

export function Pagination({ page, pageSize, total, onPage, noun = 'items' }: { page: number; pageSize: number; total: number; onPage: (p: number) => void; noun?: string }) {
  const pages = Math.max(1, Math.ceil(total / pageSize))
  const from = total === 0 ? 0 : (page - 1) * pageSize + 1
  const to = Math.min(total, page * pageSize)
  return (
    <nav className="table-foot" aria-label="Pagination">
      <span>{total === 0 ? `No ${noun}` : `${from.toLocaleString('en-IN')}–${to.toLocaleString('en-IN')} of ${total.toLocaleString('en-IN')} ${noun}`}</span>
      <span className="pager">
        <Button variant="secondary" size="sm" iconOnly icon="chevronLeft" aria-label="Previous page" disabled={page <= 1} onClick={() => onPage(page - 1)} />
        <span aria-live="polite">Page {page} of {pages}</span>
        <Button variant="secondary" size="sm" iconOnly icon="chevronRight" aria-label="Next page" disabled={page >= pages} onClick={() => onPage(page + 1)} />
      </span>
    </nav>
  )
}

export function Avatar({ name, size }: { name: string; size?: 'lg' }) {
  const parts = name.trim().split(/\s+/).filter(Boolean)
  const ini = ((parts[0]?.[0] ?? '?') + (parts.length > 1 ? parts[parts.length - 1][0] : '')).toUpperCase()
  return <span className={`avatar${size ? ' ' + size : ''}`} aria-hidden>{ini}</span>
}

/* ------------------------------------------------------------------ states */
export function Skeleton({ w, h = 14, r }: { w?: number | string; h?: number | string; r?: number }) {
  return <span className="skel" style={{ width: w ?? '100%', height: h, borderRadius: r }} aria-hidden />
}
export function SkeletonRows({ rows = 6, cols = 5 }: { rows?: number; cols?: number }) {
  return (
    <div role="status" aria-label="Loading" className="skel-table">
      {Array.from({ length: rows }, (_, i) => (
        <div key={i} className="skel-row" style={{ gridTemplateColumns: `2fr ${'1fr '.repeat(cols - 1)}` }}>
          {Array.from({ length: cols }, (_, j) => <Skeleton key={j} w={j === 0 ? '78%' : '56%'} />)}
        </div>
      ))}
    </div>
  )
}
export function SkeletonCard({ lines = 3, height }: { lines?: number; height?: number }) {
  return (
    <div role="status" aria-label="Loading" style={{ display: 'grid', gap: 10, minHeight: height }}>
      <Skeleton w="40%" h={16} />
      {Array.from({ length: lines }, (_, i) => <Skeleton key={i} w={`${92 - i * 14}%`} />)}
    </div>
  )
}

export function Empty({ title, children, icon = 'box', action }: { title: string; children?: ReactNode; icon?: IconName; action?: ReactNode }) {
  return (
    <div className="empty">
      <span className="ico"><Icon name={icon} size={22} /></span>
      <b>{title}</b>
      {children && <p>{children}</p>}
      {action && <div className="row">{action}</div>}
    </div>
  )
}

export function ErrorNote({ error, onRetry }: { error: ApiError | Error | null; onRetry?: () => void }) {
  if (!error) return null
  const code = (error as ApiError).code
  const notConfigured = code === 'NOT_CONFIGURED'
  return (
    <div className="note bad" role="alert">
      <Icon name="alert" size={17} />
      <div className="grow">
        <b>{notConfigured ? 'Gnani key needed. ' : 'Something went wrong. '}</b>
        {error.message}{' '}
        {notConfigured && <Link to="/settings">Open Settings</Link>}
        {onRetry && !notConfigured && <Button variant="link" onClick={onRetry}>Try again</Button>}
      </div>
    </div>
  )
}

export function Note({ tone = 'info', children, action }: { tone?: 'info' | 'warn' | 'ok' | 'bad'; children: ReactNode; action?: ReactNode }) {
  return (
    <div className={`note ${tone}`} role={tone === 'bad' ? 'alert' : undefined}>
      <Icon name={tone === 'ok' ? 'check' : tone === 'info' ? 'info' : 'alert'} size={17} />
      <div className="grow">{children}</div>
      {action}
    </div>
  )
}

export function Spinner({ label = 'Loading' }: { label?: string }) {
  return <div className="row muted" role="status"><span className="spinner" aria-hidden /> {label}...</div>
}

/* ------------------------------------------------------------------ provenance labels (what kind of record is this?) */
const SOURCE: Record<string, { label: string; tone?: 'ok' | 'warn' | 'info' | 'accent'; title: string }> = {
  curated: { label: 'Curated staple', tone: 'info', title: 'Hand-written staple item shipped with the demo (names in Gujarati, Hindi and English). Not from a dataset.' },
  off_india: { label: 'Open Food Facts', tone: 'accent', title: 'Imported from the Open Food Facts reference catalogue (ODbL). Name, brand and pack size are sourced; the price is the shop\'s own.' },
  manual: { label: 'Added by shop', title: 'Entered by the shopkeeper.' },
}
export function SourceBadge({ source }: { source: string }) {
  const s = SOURCE[source] ?? { label: source, title: source }
  return <Badge tone={s.tone} title={s.title}>{s.label}</Badge>
}
export function PriceBasisBadge({ basis }: { basis: string }) {
  return basis === 'demo'
    ? <Badge tone="warn" title="Placeholder price for the demo. Replace it with your own price.">Demo price</Badge>
    : <Badge tone="ok" title="Price entered by the shopkeeper.">Shop price</Badge>
}
export function DemoBadge({ title = 'Generated demo data. Not a real customer or sale.' }: { title?: string }) {
  return <Badge tone="plain" title={title}>Demo</Badge>
}

/** Debounce wrapper for local input state that reports upwards after the user pauses. */
export function useLocalInput(initial: string, onSettled: (v: string) => void, ms = 250): [string, (v: string) => void] {
  const [v, setV] = useState(initial)
  useEffect(() => { setV(initial) }, [initial])
  useEffect(() => {
    if (v === initial) return
    const t = setTimeout(() => onSettled(v), ms)
    return () => clearTimeout(t)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [v])
  return [v, setV]
}
