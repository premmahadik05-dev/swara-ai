import type { SalesPoint } from '../types'

export interface Compare { cur: number; prev: number; delta: number | null }

/** Percent change from prev to cur. `null` when there is nothing to compare against (prev = 0). */
export function pctChange(cur: number, prev: number): number | null {
  if (!(prev > 0)) return null
  return ((cur - prev) / prev) * 100
}

/** Fraction of the earlier window's periods that must contain at least one order before a comparison is shown. */
export const MIN_COVERAGE = 0.5

/**
 * Compare the last `n` complete periods with the `n` before them. A period still in progress (`partial`) is left out of both
 * sides, so a half-finished day is never compared against a full one. `delta` is null unless the earlier window is complete
 * (n periods) and has orders in at least half of them: a shop (or demo) that started recording last month would otherwise
 * show "+2000%", which is arithmetic, not a trend.
 */
export function comparePeriods(series: SalesPoint[], n: number, pick: (p: SalesPoint) => number): Compare {
  const done = series.filter((p) => !p.partial)
  const cur = done.slice(-n)
  const prev = done.slice(-2 * n, -n)
  const sum = (a: SalesPoint[]) => a.reduce((t, p) => t + pick(p), 0)
  const c = sum(cur), p = sum(prev)
  return { cur: c, prev: p, delta: comparable(prev, n) ? pctChange(c, p) : null }
}

/** True when `prev` is a full window of n periods and enough of them actually saw sales. */
export function comparable(prev: SalesPoint[], n: number): boolean {
  return prev.length === n && prev.filter((p) => p.orders > 0).length >= n * MIN_COVERAGE
}

/** Average order value now vs the earlier window, under the same rules as `comparePeriods`. */
export function compareAov(series: SalesPoint[], n: number): Compare {
  const done = series.filter((p) => !p.partial)
  const cur = done.slice(-n), prev = done.slice(-2 * n, -n)
  const c = averageOrderValue(cur), p = averageOrderValue(prev)
  return { cur: c, prev: p, delta: comparable(prev, n) ? pctChange(c, p) : null }
}

/** Average order value over a run of periods = total sales / total orders (not the mean of per-period averages). */
export function averageOrderValue(series: SalesPoint[]): number {
  const rev = series.reduce((t, p) => t + p.revenue_paise, 0)
  const orders = series.reduce((t, p) => t + p.orders, 0)
  return orders ? Math.round(rev / orders) : 0
}
