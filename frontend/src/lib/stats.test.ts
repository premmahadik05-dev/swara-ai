import { describe, expect, it } from 'vitest'
import { averageOrderValue, compareAov, comparable, comparePeriods, pctChange } from './stats'
import type { SalesPoint } from '../types'

const pt = (revenue_paise: number, orders: number, partial = false): SalesPoint => ({ period: 'x', revenue_paise, orders, avg_basket_paise: orders ? Math.round(revenue_paise / orders) : 0, partial })

describe('pctChange', () => {
  it('is a plain percentage', () => { expect(pctChange(120, 100)).toBeCloseTo(20); expect(pctChange(50, 100)).toBeCloseTo(-50) })
  it('is null, never Infinity or 0%, when there is nothing to compare with', () => { expect(pctChange(100, 0)).toBeNull(); expect(pctChange(0, 0)).toBeNull() })
})

describe('comparePeriods', () => {
  it('compares the last n complete periods with the n before', () => {
    const s = [pt(100, 1), pt(100, 1), pt(200, 1), pt(200, 1)]
    expect(comparePeriods(s, 2, (p) => p.revenue_paise)).toEqual({ cur: 400, prev: 200, delta: 100 })
  })
  it('leaves the period in progress out of both sides, so half a day is never set against a whole one', () => {
    const s = [pt(100, 1), pt(100, 1), pt(200, 1), pt(200, 1), pt(50, 1, true)]
    expect(comparePeriods(s, 2, (p) => p.revenue_paise)).toEqual({ cur: 400, prev: 200, delta: 100 })
  })
  it('gives no change figure when the earlier window is incomplete', () => {
    const s = [pt(100, 1), pt(200, 1), pt(200, 1)]       // only 1 earlier period for n = 2
    const r = comparePeriods(s, 2, (p) => p.revenue_paise)
    expect(r.cur).toBe(400)
    expect(r.delta).toBeNull()
  })
  it('gives no change figure when the earlier window had no sales', () => {
    const s = [pt(0, 0), pt(0, 0), pt(200, 1), pt(200, 1)]
    expect(comparePeriods(s, 2, (p) => p.revenue_paise).delta).toBeNull()
  })
  it('gives no change figure when fewer than half of the earlier periods had any order (a shop that only just started recording)', () => {
    // n = 4: earlier window has orders on 1 of 4 periods -> 25% coverage -> arithmetic, not a trend
    const s = [pt(0, 0), pt(0, 0), pt(0, 0), pt(100, 1), pt(200, 1), pt(200, 1), pt(200, 1), pt(200, 1)]
    const r = comparePeriods(s, 4, (p) => p.revenue_paise)
    expect(r.cur).toBe(800)
    expect(r.prev).toBe(100)
    expect(r.delta).toBeNull()
  })
  it('does give a figure when exactly half of the earlier periods had orders', () => {
    const s = [pt(0, 0), pt(100, 1), pt(0, 0), pt(100, 1), pt(150, 1), pt(150, 1), pt(150, 1), pt(150, 1)]
    expect(comparePeriods(s, 4, (p) => p.revenue_paise).delta).toBeCloseTo(200)
  })
  it('handles an empty series', () => { expect(comparePeriods([], 7, (p) => p.orders)).toEqual({ cur: 0, prev: 0, delta: null }) })
})

describe('averageOrderValue', () => {
  it('is total sales over total orders, not the mean of daily averages', () => {
    // day 1: 1 order of ₹100; day 2: 9 orders of ₹10 each. Mean of averages would be ₹55; the real figure is ₹19.
    expect(averageOrderValue([pt(10000, 1), pt(9000, 9)])).toBe(1900)
  })
  it('is 0 with no orders', () => { expect(averageOrderValue([pt(0, 0)])).toBe(0); expect(averageOrderValue([])).toBe(0) })
})

describe('comparable', () => {
  it('needs a full window of n periods', () => { expect(comparable([pt(1, 1)], 2)).toBe(false); expect(comparable([pt(1, 1), pt(1, 1)], 2)).toBe(true) })
  it('needs orders in at least half of the periods', () => {
    expect(comparable([pt(0, 0), pt(0, 0), pt(0, 0), pt(5, 1)], 4)).toBe(false)
    expect(comparable([pt(0, 0), pt(0, 0), pt(5, 1), pt(5, 1)], 4)).toBe(true)
  })
})

describe('compareAov', () => {
  it('compares total-sales-over-total-orders now vs before, leaving the unfinished period out', () => {
    const s = [pt(1000, 1), pt(1000, 1), pt(3000, 1), pt(3000, 1), pt(1, 1, true)]
    expect(compareAov(s, 2)).toEqual({ cur: 3000, prev: 1000, delta: 200 })
  })
  it('gives no change figure on a thin earlier window, same rule as sales and orders', () => {
    const s = [pt(0, 0), pt(0, 0), pt(0, 0), pt(1000, 1), pt(3000, 1), pt(3000, 1), pt(3000, 1), pt(3000, 1)]
    expect(compareAov(s, 4).delta).toBeNull()
  })
})
