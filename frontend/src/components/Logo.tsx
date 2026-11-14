import { useId } from 'react'
import { LOCKUP, LOCKUP_COMPACT, SYMBOL, SYMBOL_COMPACT } from './logoPaths'

/**
 * SWARA AI logo, drawn from the generated geometry in logoPaths.ts (built by scripts/brand/build_logo.py).
 * The mark is a gold gradient and the wordmark reads exactly "SWARA AI". Colours come from tokens (--logo-*, --text),
 * so one component is right on the white and ivory surfaces of the (light-only) design. `compact` is the two-strand S that
 * stays clear below about 40 px.
 */
type Geo = { readonly w: number; readonly h: number; readonly x0: number; readonly y0: number; readonly paths: readonly string[] }

function useGradientId() {
  return 'swg' + useId().replace(/[^a-zA-Z0-9]/g, '')
}

function Gradient({ id, geo }: { id: string; geo: Geo }) {
  return (
    <linearGradient id={id} gradientUnits="userSpaceOnUse" x1={geo.x0} y1={geo.y0} x2={geo.x0 + geo.w} y2={geo.y0 + geo.h}>
      <stop offset="0" style={{ stopColor: 'var(--logo-hi)' }} />
      <stop offset="0.5" style={{ stopColor: 'var(--logo-mid)' }} />
      <stop offset="1" style={{ stopColor: 'var(--logo-lo)' }} />
    </linearGradient>
  )
}

function Strands({ geo, gid }: { geo: Geo; gid: string }) {
  return (
    <g transform={`translate(${-geo.x0} ${-geo.y0})`} fill={`url(#${gid})`}>
      {geo.paths.map((d, i) => <path key={i} d={d} />)}
    </g>
  )
}

type Common = { className?: string; /** hide from assistive tech when a parent link/button already carries the name */ decorative?: boolean }
const a11y = (decorative?: boolean) => (decorative ? { 'aria-hidden': true as const, focusable: 'false' as const } : { role: 'img' as const, 'aria-label': 'SWARA AI' })

/** The S on its own. `size` is the height in px. */
export function LogoMark({ size = 32, compact = false, className, decorative }: Common & { size?: number; compact?: boolean }) {
  const gid = useGradientId()
  const geo: Geo = compact ? SYMBOL_COMPACT : SYMBOL
  const pad = compact ? 4 : 6
  const w = geo.w + 2 * pad
  const h = geo.h + 2 * pad
  return (
    <svg className={className} width={(size * w) / h} height={size} viewBox={`0 0 ${w} ${h}`} {...a11y(decorative)}>
      <defs><Gradient id={gid} geo={geo} /></defs>
      <g transform={`translate(${pad} ${pad})`}><Strands geo={geo} gid={gid} /></g>
    </svg>
  )
}

/** Symbol + the name "SWARA AI". `height` is the full height in px. */
export function Logo({ height = 40, compact = false, className, decorative }: Common & { height?: number; compact?: boolean }) {
  const gid = useGradientId()
  const L = compact ? LOCKUP_COMPACT : LOCKUP
  const geo: Geo = compact ? SYMBOL_COMPACT : SYMBOL
  return (
    <svg className={className} width={(height * L.width) / L.height} height={height} viewBox={`0 0 ${L.width} ${L.height}`} {...a11y(decorative)}>
      <defs><Gradient id={gid} geo={geo} /></defs>
      <g transform={`translate(${L.pad} ${L.pad}) scale(${L.scale})`}><Strands geo={geo} gid={gid} /></g>
      <path d={L.swara} fill="var(--text)" transform={`translate(${L.tx} ${L.base})`} />
      <path d={L.ai} fill="var(--text)" transform={`translate(${L.ai_x} ${L.base})`} />
    </svg>
  )
}
