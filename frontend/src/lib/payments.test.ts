import { describe, expect, it } from 'vitest'
import { PAY_STATUS_TEXT, attentionText, cashReceivedProblem, cashSuggestions, isPaid, newKey, orderPaymentLabel, rupeesToPaise, upiReferenceProblem } from './payments'

describe('rupeesToPaise', () => {
  it('turns plain amounts into whole paise without floating point', () => {
    expect(rupeesToPaise('500')).toBe(50000)
    expect(rupeesToPaise('₹ 1,234.50')).toBe(123450)
    expect(rupeesToPaise('0.1')).toBe(10)
    expect(rupeesToPaise('19.99')).toBe(1999)
  })
  it('refuses anything that is not a plain amount', () => {
    for (const bad of ['', 'abc', '1.234', '-5', '1e3', '12,3,4x', '1..2']) expect(rupeesToPaise(bad)).toBeNull()
  })
})

describe('upiReferenceProblem', () => {
  it('accepts a bank reference and rejects short or odd ones, like the server', () => {
    expect(upiReferenceProblem('412345678901')).toBeNull()
    expect(upiReferenceProblem('AB-12/cd 9')).toBeNull()
    expect(upiReferenceProblem('abc')).not.toBeNull()
    expect(upiReferenceProblem('x'.repeat(41))).not.toBeNull()
    expect(upiReferenceProblem('12345<script>')).not.toBeNull()
  })
})

describe('cashSuggestions', () => {
  it('offers a few round amounts above the bill, never the bill itself', () => {
    const s = cashSuggestions(17200)
    expect(s.length).toBeGreaterThan(0)
    expect(s.length).toBeLessThanOrEqual(3)
    expect(s.every((v) => v > 17200)).toBe(true)
    expect(new Set(s).size).toBe(s.length)
  })
})

describe('cashReceivedProblem', () => {
  it('follows the server: not less than the bill, not an obvious slip', () => {
    expect(cashReceivedProblem(null, 17200)).toMatch(/Enter the amount/)
    expect(cashReceivedProblem(17199, 17200)).toBe('That is less than the bill of \u20b9172.')
    expect(cashReceivedProblem(17200, 17200)).toBeNull()
    expect(cashReceivedProblem(50000, 17200)).toBeNull()
    // the server's ceiling is 20 x the bill + Rs 1000: the amount at the ceiling passes, one paisa over does not
    expect(cashReceivedProblem(17200 * 20 + 100000, 17200)).toBeNull()
    expect(cashReceivedProblem(17200 * 20 + 100001, 17200)).toBe('That amount looks wrong. Check it and try again.')
  })
})

describe('labels', () => {
  it('says "Not recorded" for an order with no payment, and never "unpaid"', () => {
    expect(orderPaymentLabel(undefined).text).toBe('Not recorded')
    expect(PAY_STATUS_TEXT.none).not.toMatch(/unpaid/i)
  })
  it('names the way paid only once money was collected', () => {
    const base = { paid_paise: 0, refunded_paise: 0, payment_id: 1, pending_payment_id: null }
    expect(orderPaymentLabel({ ...base, status: 'pending', method: 'upi' }).text).not.toMatch(/UPI/)
    expect(orderPaymentLabel({ ...base, status: 'paid', method: 'upi' }).text).toBe('Paid · UPI')
  })
  it('knows which states mean money was collected', () => {
    expect(isPaid('paid') && isPaid('partially_refunded') && isPaid('refunded')).toBe(true)
    expect(isPaid('pending') || isPaid('failed') || isPaid('cancelled') || isPaid('none')).toBe(false)
  })
  it('turns the server flags into plain sentences and ignores unknown absence', () => {
    expect(attentionText(null)).toBeNull()
    expect(attentionText('amount_mismatch')?.long).toMatch(/not marked paid/i)
    expect(attentionText('something_new')?.short).toBe('Needs a look')
  })
  it('makes different request keys each time', () => {
    expect(newKey()).not.toBe(newKey())
  })
})
